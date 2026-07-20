"""Secure, fail-closed staging for files supplied by the parent agent.

Every accepted file is copied atomically into ``<session workdir>/input`` and
described by a size/SHA-256 manifest.  Callers can therefore distinguish an
accepted task from one whose files were missing, malformed, or inaccessible.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass, field
from typing import Any, Iterable, List

from src.logger import get_logger

logger = get_logger(__name__)

INPUT_SUBDIR = "input"
DEFAULT_MAX_FILE_BYTES = int(
    os.getenv("SUBAGENT_MAX_INPUT_FILE_BYTES", str(200 * 1024 * 1024))
)
DEFAULT_MAX_TOTAL_BYTES = int(
    os.getenv("SUBAGENT_MAX_INPUT_TOTAL_BYTES", str(256 * 1024 * 1024))
)
DEFAULT_MAX_FILES = int(os.getenv("SUBAGENT_MAX_INPUT_FILES", "64"))
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StagedFile:
    """A file that was durably staged and verified."""

    name: str
    path: str
    size: int
    sha256: str
    source: str
    stored_name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "source": self.source,
            "stored_name": self.stored_name,
        }


@dataclass(frozen=True)
class StagingError:
    """A stable, machine-readable staging error."""

    name: str
    code: str
    error: str
    path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "name": self.name,
            "code": self.code,
            "error": self.error,
        }
        if self.path is not None:
            value["path"] = self.path
        return value


@dataclass
class StagingResult:
    requested_file_count: int = 0
    staged_files: list[StagedFile] = field(default_factory=list)
    file_errors: list[StagingError] = field(default_factory=list)

    @property
    def staged_file_count(self) -> int:
        return len(self.staged_files)

    @property
    def paths(self) -> list[str]:
        return [entry.path for entry in self.staged_files]

    @property
    def complete(self) -> bool:
        return (
            self.requested_file_count == self.staged_file_count
            and not self.file_errors
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_file_count": self.requested_file_count,
            "staged_file_count": self.staged_file_count,
            "staged_files": [entry.as_dict() for entry in self.staged_files],
            "file_errors": [entry.as_dict() for entry in self.file_errors],
        }


def _safe_name(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise ValueError("filename must be a non-empty string of at most 255 characters")
    if value in {".", ".."} or os.path.basename(value) != value:
        raise ValueError("filename must be a basename without path separators")
    if "/" in value or "\\" in value or "\x00" in value:
        raise ValueError("filename contains a forbidden character")
    return value


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _prepare_target_root(workdir: str) -> str:
    real_workdir = os.path.realpath(workdir)
    if os.path.islink(workdir):
        raise ValueError("session workdir must not be a symlink")
    os.makedirs(real_workdir, exist_ok=True)
    target_root = os.path.join(real_workdir, INPUT_SUBDIR)
    if os.path.lexists(target_root) and os.path.islink(target_root):
        raise ValueError("session input directory must not be a symlink")
    os.makedirs(target_root, exist_ok=True)
    real_target = os.path.realpath(target_root)
    if not _inside(real_target, real_workdir) or real_target == real_workdir:
        raise ValueError("session input directory resolves outside the workdir")
    return real_target


def _unique_destination(target_root: str, requested_name: str) -> tuple[str, str]:
    name = requested_name
    counter = 1
    while os.path.lexists(os.path.join(target_root, name)):
        stem, ext = os.path.splitext(requested_name)
        name = f"{stem}_{counter}{ext}"
        counter += 1
    destination = os.path.join(target_root, name)
    if not _inside(os.path.realpath(destination), target_root):
        raise ValueError("destination resolves outside the session input directory")
    return name, destination


def _atomic_write(
    target_root: str,
    requested_name: str,
    chunks: Iterable[bytes],
    *,
    max_bytes: int,
) -> tuple[str, int, str, str]:
    stored_name, destination = _unique_destination(target_root, requested_name)
    fd, temporary = tempfile.mkstemp(prefix=".staging-", dir=target_root)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            for chunk in chunks:
                if not isinstance(chunk, bytes):
                    raise ValueError("staging source yielded non-bytes data")
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"file exceeds {max_bytes} byte limit")
                handle.write(chunk)
                digest.update(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        return os.path.abspath(destination), size, digest.hexdigest(), stored_name
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _decode_chunks(encoded: str) -> Iterable[bytes]:
    # Strict validation prevents corrupt/truncated input from being accepted.
    try:
        yield base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"invalid base64 content: {exc}") from exc


def _source_chunks(path: str) -> Iterable[bytes]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("source is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
    finally:
        os.close(fd)


def _validate_source(path: str, source_root: str, forbidden_root: str | None) -> str:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("source path must be a non-empty string")
    absolute = os.path.abspath(path)
    if os.path.islink(absolute):
        raise ValueError("symbolic-link sources are not allowed")
    real_source = os.path.realpath(absolute)
    real_root = os.path.realpath(source_root)
    if not _inside(real_source, real_root) or real_source == real_root:
        raise ValueError("source resolves outside SUBAGENT_INPUT_SOURCE_ROOT")
    if forbidden_root:
        real_forbidden = os.path.realpath(forbidden_root)
        if _inside(real_source, real_forbidden):
            raise ValueError("cross-session workdir sources are not allowed")
    if not os.path.exists(real_source):
        raise FileNotFoundError("source file does not exist")
    return real_source


def _verify_expected(item: dict[str, Any], size: int, sha256: str) -> None:
    expected_size = item.get("size")
    if expected_size is not None:
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            raise ValueError("declared size must be a non-negative integer")
        if expected_size != size:
            raise ValueError(f"size mismatch: expected {expected_size}, staged {size}")
    expected_hash = item.get("sha256")
    if expected_hash is not None:
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ValueError("declared sha256 must contain 64 hexadecimal characters")
        try:
            int(expected_hash, 16)
        except ValueError as exc:
            raise ValueError("declared sha256 must be hexadecimal") from exc
        if expected_hash.lower() != sha256:
            raise ValueError("sha256 mismatch")


def stage_request_inputs(
    workdir: str,
    raw_paths: Iterable[Any] | None,
    files_content: list[dict[str, Any]] | None,
    *,
    source_root: str,
    forbidden_source_root: str | None = None,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
) -> StagingResult:
    """Stage a logical file set and return a complete manifest.

    A basename present in both ``raw_paths`` and ``files_content`` represents
    one logical file. Inline content is authoritative and the path is a
    fallback only when decoding or integrity verification fails.
    """
    result = StagingResult()
    try:
        target_root = _prepare_target_root(workdir)
    except Exception as exc:
        result.file_errors.append(StagingError("*", "target_unavailable", str(exc)))
        return result

    if raw_paths is None:
        raw_items: list[Any] = []
    elif isinstance(raw_paths, (list, tuple)):
        raw_items = list(raw_paths)
    else:
        result.file_errors.append(
            StagingError("*", "invalid_schema", "input_files must be an array")
        )
        return result
    if files_content is None:
        content_items: list[Any] = []
    elif isinstance(files_content, list):
        content_items = list(files_content)
    else:
        result.file_errors.append(
            StagingError("*", "invalid_schema", "input_files_content must be an array")
        )
        return result

    by_path_name: dict[str, dict[str, Any]] = {}
    inline_by_name: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for raw in raw_items:
        item = {"path": raw} if isinstance(raw, str) else raw
        path = item.get("path") if isinstance(item, dict) else None
        candidate = item.get("name") if isinstance(item, dict) else None
        candidate = candidate or (os.path.basename(path) if isinstance(path, str) else "")
        try:
            name = _safe_name(candidate)
        except ValueError as exc:
            result.file_errors.append(StagingError(str(candidate or "*"), "invalid_name", str(exc), str(path) if path else None))
            continue
        if name in by_path_name:
            result.file_errors.append(StagingError(name, "duplicate_name", "duplicate input_files basename", str(path)))
            continue
        by_path_name[name] = dict(item)
        if name not in order:
            order.append(name)

    for raw in content_items:
        if not isinstance(raw, dict):
            result.file_errors.append(StagingError("*", "invalid_schema", "inline file entry must be an object"))
            continue
        try:
            name = _safe_name(raw.get("name"))
        except ValueError as exc:
            result.file_errors.append(StagingError(str(raw.get("name") or "*"), "invalid_name", str(exc)))
            continue
        if name in inline_by_name:
            result.file_errors.append(StagingError(name, "duplicate_name", "duplicate input_files_content name"))
            continue
        inline_by_name[name] = raw
        if name not in order:
            order.append(name)

    result.requested_file_count = len(order)
    if len(order) > max_files:
        result.file_errors.append(
            StagingError("*", "too_many_files", f"requested {len(order)} files; limit is {max_files}")
        )
        return result

    total_size = 0
    preexisting_errors = {entry.name for entry in result.file_errors}
    for name in order:
        if name in preexisting_errors:
            continue
        inline = inline_by_name.get(name)
        path_item = by_path_name.get(name)
        errors: list[tuple[str, Exception, str | None]] = []
        staged: StagedFile | None = None
        staged_path: str | None = None

        if inline is not None:
            encoded = inline.get("content_base64")
            if not isinstance(encoded, str):
                errors.append(("invalid_content", ValueError("content_base64 must be a string"), None))
            else:
                try:
                    staged_path, size, digest, stored_name = _atomic_write(
                        target_root,
                        name,
                        _decode_chunks(encoded),
                        max_bytes=min(max_file_bytes, max_total_bytes - total_size),
                    )
                    _verify_expected(inline, size, digest)
                    staged = StagedFile(name, staged_path, size, digest, "inline", stored_name)
                except Exception as exc:
                    # Integrity failure must remove the just-staged file.
                    if staged_path and os.path.isfile(staged_path):
                        try:
                            os.unlink(staged_path)
                        except OSError:
                            pass
                    errors.append(("invalid_content", exc, None))

        if staged is None and path_item is not None:
            raw_path = path_item.get("path")
            try:
                source = _validate_source(raw_path, source_root, forbidden_source_root)
                path, size, digest, stored_name = _atomic_write(
                    target_root,
                    name,
                    _source_chunks(source),
                    max_bytes=min(max_file_bytes, max_total_bytes - total_size),
                )
                _verify_expected(path_item, size, digest)
                staged = StagedFile(
                    name,
                    path,
                    size,
                    digest,
                    str(path_item.get("_source") or (
                        "path_fallback" if inline is not None else "path"
                    )),
                    stored_name,
                )
            except Exception as exc:
                errors.append(("source_unavailable", exc, str(raw_path) if raw_path is not None else None))

        if staged is not None:
            total_size += staged.size
            result.staged_files.append(staged)
            if total_size > max_total_bytes:
                try:
                    os.unlink(staged.path)
                except OSError:
                    pass
                result.staged_files.pop()
                result.file_errors.append(
                    StagingError(name, "total_size_exceeded", f"aggregate input exceeds {max_total_bytes} bytes")
                )
            continue

        if errors:
            code, exc, failed_path = errors[-1]
            details = "; ".join(str(error) for _, error, _ in errors)
            result.file_errors.append(StagingError(name, code, details, failed_path))
        else:
            result.file_errors.append(StagingError(name, "missing_content", "no usable path or inline content supplied"))

    return result


def rehydrate_staged_inputs(
    workdir: str,
    previous_workdir: str,
    previous_manifest: dict[str, Any],
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> StagingResult:
    """Copy verified input files from an explicitly selected prior session.

    This is separate from caller path staging: arbitrary requests may never
    read a sibling session, while an authenticated ``previous_session_id``
    continuation can rehydrate only files recorded in that session's manifest.
    """
    result = StagingResult()
    entries = previous_manifest.get("staged_files") if isinstance(previous_manifest, dict) else None
    if not entries:
        return result
    if not isinstance(entries, list):
        result.file_errors.append(StagingError("*", "invalid_previous_manifest", "prior staged_files is not an array"))
        return result
    try:
        target_root = _prepare_target_root(workdir)
    except Exception as exc:
        result.file_errors.append(StagingError("*", "target_unavailable", str(exc)))
        return result

    previous_input = os.path.realpath(os.path.join(previous_workdir, INPUT_SUBDIR))
    result.requested_file_count = len(entries)
    total = 0
    for raw in entries:
        if not isinstance(raw, dict):
            result.file_errors.append(StagingError("*", "invalid_previous_manifest", "prior file entry is not an object"))
            continue
        try:
            name = _safe_name(raw.get("name"))
            source = os.path.realpath(str(raw.get("path") or ""))
            if not _inside(source, previous_input) or source == previous_input:
                raise ValueError("prior file path resolves outside its session input directory")
            if os.path.islink(source) or not os.path.isfile(source):
                raise ValueError("prior staged file is unavailable or a symlink")
            destination, size, digest, stored_name = _atomic_write(
                target_root,
                name,
                _source_chunks(source),
                max_bytes=min(max_file_bytes, max_total_bytes - total),
            )
            _verify_expected(raw, size, digest)
            total += size
            result.staged_files.append(
                StagedFile(name, destination, size, digest, "previous_session", stored_name)
            )
        except Exception as exc:
            result.file_errors.append(
                StagingError(str(raw.get("name") or "*"), "previous_file_unavailable", str(exc), str(raw.get("path") or ""))
            )
    return result


def _legacy_source_root(workdir: str) -> str:
    configured = os.getenv("SUBAGENT_INPUT_SOURCE_ROOT") or os.getenv("SUBAGENT_STORAGE_DIR")
    if configured:
        return configured
    workdir_base = os.path.realpath(os.getenv("WORKDIR_BASE", os.path.dirname(workdir)))
    return os.path.dirname(workdir_base)


def stage_inputs_into_workdir(workdir: str, raw_paths: Iterable[str]) -> List[str]:
    """Backward-compatible wrapper returning only successfully staged paths."""
    items = list(raw_paths)
    if not items:
        return []
    # Legacy helper callers expect duplicate basenames to be suffixed rather
    # than rejected. The HTTP protocol uses ``stage_request_inputs`` directly
    # and remains strict/fail-closed.
    staged: list[str] = []
    for item in items:
        staged.extend(stage_request_inputs(
            workdir,
            [item],
            [],
            source_root=_legacy_source_root(workdir),
            forbidden_source_root=os.getenv("WORKDIR_BASE"),
        ).paths)
    return staged


def stage_inputs_from_content(workdir: str, files_content: list[dict]) -> list[str]:
    """Backward-compatible wrapper returning only successfully staged paths."""
    if not files_content:
        return []
    staged: list[str] = []
    for item in files_content:
        staged.extend(stage_request_inputs(
            workdir,
            [],
            [item],
            source_root=_legacy_source_root(workdir),
            forbidden_source_root=os.getenv("WORKDIR_BASE"),
        ).paths)
    return staged


def is_input_path(workdir: str, path: str) -> bool:
    """Return whether ``path`` is a real file below this session's input dir."""
    root = os.path.realpath(os.path.join(workdir, INPUT_SUBDIR))
    candidate = os.path.realpath(path)
    return _inside(candidate, root)
