"""Authenticated, resumable file uploads for cross-machine input transfer."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from typing import Any

from src.logger import get_logger

logger = get_logger(__name__)

UPLOAD_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_CONTENT_RANGE_PATTERN = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class UploadError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_upload", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _safe_filename(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise UploadError("filename must be a non-empty string of at most 255 characters")
    if value in {".", ".."} or os.path.basename(value) != value or "/" in value or "\\" in value or "\x00" in value:
        raise UploadError("filename must be a safe basename")
    return value


def _sha256(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise UploadError("sha256 must contain 64 hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise UploadError("sha256 must be hexadecimal") from exc
    return value.lower()


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    match = _CONTENT_RANGE_PATTERN.fullmatch(value or "")
    if not match:
        raise UploadError("Content-Range must use 'bytes <start>-<end>/<total>'")
    start, end, total = (int(part) for part in match.groups())
    if start < 0 or end < start or total < 0 or end >= total:
        raise UploadError("Content-Range is outside the declared upload size")
    return start, end, total


class UploadStore:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        self.max_file_bytes = int(os.getenv("SUBAGENT_MAX_UPLOAD_FILE_BYTES", str(200 * 1024 * 1024)))
        self.max_total_bytes = int(os.getenv("SUBAGENT_MAX_UPLOAD_TOTAL_BYTES", str(512 * 1024 * 1024)))
        self.max_chunk_bytes = int(os.getenv("SUBAGENT_MAX_UPLOAD_CHUNK_BYTES", str(8 * 1024 * 1024)))
        self.incomplete_ttl = int(os.getenv("SUBAGENT_UPLOAD_INCOMPLETE_TTL_S", "900"))
        self.complete_ttl = int(os.getenv("SUBAGENT_UPLOAD_COMPLETE_TTL_S", "3600"))
        self._lock = threading.RLock()
        os.makedirs(self.root, exist_ok=True)
        if os.path.islink(self.root):
            raise RuntimeError("SUBAGENT_UPLOAD_DIR must not be a symlink")
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _directory(self, upload_id: str) -> str:
        if not isinstance(upload_id, str) or not UPLOAD_ID_PATTERN.fullmatch(upload_id):
            raise UploadError("upload_id must be 32 lowercase hexadecimal characters")
        path = os.path.realpath(os.path.join(self.root, upload_id))
        if os.path.commonpath((path, self.root)) != self.root or path == self.root:
            raise UploadError("upload_id resolves outside upload root")
        return path

    def _metadata_path(self, upload_id: str) -> str:
        return os.path.join(self._directory(upload_id), "metadata.json")

    @staticmethod
    def _atomic_json(path: str, value: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".metadata-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def _read(self, upload_id: str) -> dict[str, Any]:
        path = self._metadata_path(upload_id)
        try:
            with open(path, encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError as exc:
            raise UploadError("upload_id was not found or expired", code="upload_not_found", status=404) from exc
        if value.get("upload_id") != upload_id:
            raise UploadError("upload metadata is corrupt", code="upload_corrupt", status=500)
        return value

    def _reserved_bytes(self) -> int:
        total = 0
        for name in os.listdir(self.root):
            if not UPLOAD_ID_PATTERN.fullmatch(name):
                continue
            try:
                metadata = self._read(name)
                if metadata.get("state") != "consumed":
                    total += int(metadata.get("size", 0))
            except (UploadError, TypeError, ValueError):
                continue
        return total

    def initiate(
        self,
        *,
        filename: Any,
        size: Any,
        sha256: Any,
        upload_id: Any = None,
    ) -> tuple[dict[str, Any], bool]:
        filename = _safe_filename(filename)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise UploadError("size must be a non-negative integer")
        if size > self.max_file_bytes:
            raise UploadError(
                f"file exceeds {self.max_file_bytes} byte upload limit",
                code="file_too_large",
                status=413,
            )
        sha256 = _sha256(sha256)
        if upload_id is None:
            upload_id = uuid.uuid4().hex
        directory = self._directory(upload_id)
        with self._lock:
            if os.path.exists(self._metadata_path(upload_id)):
                existing = self._read(upload_id)
                identity = (existing.get("filename"), existing.get("size"), existing.get("sha256"))
                if identity != (filename, size, sha256):
                    raise UploadError("upload_id is already bound to different content", code="upload_conflict", status=409)
                return existing, True
            if self._reserved_bytes() + size > self.max_total_bytes:
                raise UploadError(
                    "aggregate active upload quota would be exceeded",
                    code="upload_quota_exceeded",
                    status=429,
                )
            os.makedirs(os.path.join(directory, "chunks"), exist_ok=False)
            now = time.time()
            metadata = {
                "version": 1,
                "upload_id": upload_id,
                "filename": filename,
                "size": size,
                "sha256": sha256,
                "state": "uploading",
                "chunks": {},
                "claimed_session_id": None,
                "created_at": now,
                "last_activity": now,
            }
            self._atomic_json(self._metadata_path(upload_id), metadata)
            return metadata, False

    def put_chunk(
        self,
        upload_id: str,
        index: int,
        content_range: str | None,
        data: bytes,
    ) -> tuple[dict[str, Any], bool]:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index > 100000:
            raise UploadError("chunk index must be an integer between 0 and 100000")
        start, end, total = parse_content_range(content_range)
        if len(data) != end - start + 1:
            raise UploadError("chunk length does not match Content-Range")
        if len(data) > self.max_chunk_bytes:
            raise UploadError("chunk exceeds configured size limit", code="chunk_too_large", status=413)
        with self._lock:
            metadata = self._read(upload_id)
            if metadata.get("state") == "complete":
                raise UploadError("upload is already complete", code="upload_complete", status=409)
            if total != metadata.get("size"):
                raise UploadError("Content-Range total differs from declared size")
            digest = hashlib.sha256(data).hexdigest()
            key = str(index)
            existing = metadata["chunks"].get(key)
            descriptor = {"index": index, "start": start, "end": end, "size": len(data), "sha256": digest}
            if existing is not None:
                if existing != descriptor:
                    raise UploadError("chunk index is already bound to different bytes", code="chunk_conflict", status=409)
                return descriptor, True
            for other in metadata["chunks"].values():
                if not (end < other["start"] or start > other["end"]):
                    raise UploadError("chunk byte range overlaps another chunk", code="chunk_overlap", status=409)
            chunk_dir = os.path.join(self._directory(upload_id), "chunks")
            fd, temporary = tempfile.mkstemp(prefix=".chunk-", dir=chunk_dir)
            destination = os.path.join(chunk_dir, f"{index:08d}.part")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            except Exception:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                raise
            metadata["chunks"][key] = descriptor
            metadata["last_activity"] = time.time()
            self._atomic_json(self._metadata_path(upload_id), metadata)
            return descriptor, False

    def complete(self, upload_id: str) -> tuple[dict[str, Any], bool]:
        with self._lock:
            metadata = self._read(upload_id)
            if metadata.get("state") == "complete":
                return metadata, True
            chunks = sorted(metadata["chunks"].values(), key=lambda item: item["start"])
            expected_offset = 0
            for descriptor in chunks:
                if descriptor["start"] != expected_offset:
                    raise UploadError("uploaded chunks do not form a contiguous file", code="upload_incomplete", status=409)
                expected_offset = descriptor["end"] + 1
            if expected_offset != metadata["size"]:
                if not (metadata["size"] == 0 and not chunks):
                    raise UploadError("uploaded chunks do not cover the declared size", code="upload_incomplete", status=409)

            directory = self._directory(upload_id)
            fd, temporary = tempfile.mkstemp(prefix=".assembling-", dir=directory)
            digest = hashlib.sha256()
            size = 0
            try:
                with os.fdopen(fd, "wb") as output:
                    for descriptor in chunks:
                        chunk_path = os.path.join(directory, "chunks", f"{descriptor['index']:08d}.part")
                        if os.path.islink(chunk_path):
                            raise UploadError("chunk symlink detected", code="upload_corrupt", status=409)
                        chunk_digest = hashlib.sha256()
                        with open(chunk_path, "rb") as source:
                            for block in iter(lambda: source.read(1024 * 1024), b""):
                                size += len(block)
                                digest.update(block)
                                chunk_digest.update(block)
                                output.write(block)
                        if chunk_digest.hexdigest() != descriptor["sha256"]:
                            raise UploadError("chunk checksum mismatch", code="upload_corrupt", status=409)
                    output.flush()
                    os.fsync(output.fileno())
                if size != metadata["size"] or digest.hexdigest() != metadata["sha256"]:
                    raise UploadError("assembled upload size/checksum mismatch", code="upload_corrupt", status=409)
                final_path = os.path.join(directory, "completed.bin")
                os.replace(temporary, final_path)
            except Exception:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                raise
            shutil.rmtree(os.path.join(directory, "chunks"), ignore_errors=True)
            metadata.update(state="complete", completed_at=time.time(), last_activity=time.time())
            self._atomic_json(self._metadata_path(upload_id), metadata)
            return metadata, False

    def claim(self, upload_id: str, session_id: str) -> dict[str, Any]:
        with self._lock:
            metadata = self._read(upload_id)
            if metadata.get("state") != "complete":
                raise UploadError("upload is not complete", code="upload_incomplete", status=409)
            claimed = metadata.get("claimed_session_id")
            if claimed not in {None, session_id}:
                raise UploadError("upload is already claimed by another session", code="upload_claimed", status=409)
            final_path = os.path.join(self._directory(upload_id), "completed.bin")
            if os.path.islink(final_path) or not os.path.isfile(final_path):
                raise UploadError("completed upload file is unavailable", code="upload_corrupt", status=409)
            metadata["claimed_session_id"] = session_id
            metadata["last_activity"] = time.time()
            self._atomic_json(self._metadata_path(upload_id), metadata)
            return {
                "path": final_path,
                "name": metadata["filename"],
                "size": metadata["size"],
                "sha256": metadata["sha256"],
                "_source": "upload",
                "upload_id": upload_id,
            }

    def release(self, upload_ids: list[str], session_id: str) -> None:
        """Release upload quota after the staged session manifest is durable."""
        with self._lock:
            for upload_id in upload_ids:
                try:
                    metadata = self._read(upload_id)
                    if metadata.get("claimed_session_id") != session_id:
                        continue
                    metadata["state"] = "consumed"
                    metadata["last_activity"] = time.time()
                    self._atomic_json(self._metadata_path(upload_id), metadata)
                    directory = self._directory(upload_id)
                    if os.path.isdir(directory) and not os.path.islink(directory):
                        shutil.rmtree(directory)
                except UploadError:
                    continue
                except OSError as exc:
                    # The consumed marker makes quota accounting safe even if
                    # Windows/AV temporarily prevents directory deletion.
                    logger.warning(
                        "Could not immediately delete consumed upload",
                        extra={"upload_id": upload_id, "error": str(exc)},
                    )

    def _cleanup_loop(self) -> None:
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                for name in os.listdir(self.root):
                    if not UPLOAD_ID_PATTERN.fullmatch(name):
                        continue
                    try:
                        metadata = self._read(name)
                        ttl = self.complete_ttl if metadata.get("state") == "complete" else self.incomplete_ttl
                        if now - float(metadata.get("last_activity", 0)) > ttl:
                            directory = self._directory(name)
                            if os.path.isdir(directory) and not os.path.islink(directory):
                                shutil.rmtree(directory)
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.warning("Upload cleanup skipped an invalid entry", extra={"upload_id": name, "error": str(exc)})
