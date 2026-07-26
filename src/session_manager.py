"""Session lifecycle, steering acknowledgements, and durable callbacks."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import shutil
import stat
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import requests

from src.logger import get_logger

logger = get_logger(__name__)

_WEBHOOK_RETRY_MAX = int(os.getenv("WEBHOOK_RETRY_MAX", "15"))
_WEBHOOK_RETRY_BASE_BACKOFF = float(os.getenv("WEBHOOK_RETRY_BASE_BACKOFF", "1.0"))
_WEBHOOK_RETRY_MAX_BACKOFF = float(os.getenv("WEBHOOK_RETRY_MAX_BACKOFF", "60.0"))
_WEBHOOK_HEALTH_CHECK_ATTEMPTS = int(os.getenv("WEBHOOK_HEALTH_CHECK_ATTEMPTS", "5"))
_WEBHOOK_HEALTH_CHECK_TIMEOUT = float(os.getenv("WEBHOOK_HEALTH_CHECK_TIMEOUT", "15.0"))
_MAX_INLINE_FILE_BYTES = int(
    os.getenv("SUBAGENT_MAX_INLINE_FILE_BYTES", str(50 * 1024 * 1024))
)
# 128 MiB raw becomes about 171 MiB after base64, safely below the bridge's
# 200 MiB callback body limit after JSON overhead.
_MAX_INLINE_TOTAL_BYTES = int(
    os.getenv("SUBAGENT_MAX_INLINE_TOTAL_BYTES", str(128 * 1024 * 1024))
)
_OUTBOX_RETRY_INTERVAL = float(os.getenv("SUBAGENT_OUTBOX_RETRY_INTERVAL", "30"))
_WEBHOOK_TOKEN = os.getenv("SUBAGENT_WEBHOOK_TOKEN", "")

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._-]{0,199}$")
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class SessionPersistenceError(RuntimeError):
    """Raised when the service cannot durably record a session transition."""


def validate_session_id(session_id: Any) -> str:
    """Return a canonical opaque session id or raise ``ValueError``.

    Slashes and aliases are intentionally not normalized: distinct HTTP ids
    must always map one-to-one to distinct work directories.
    """
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Invalid session_id: must not be empty")
    if session_id in {".", ".."}:
        raise ValueError("Invalid session_id: must not be empty or a path alias")
    if "/" in session_id or "\\" in session_id:
        raise ValueError("Invalid session_id: resolves outside workdir_base; separators are forbidden")
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(
            "Invalid session_id: expected [A-Za-z0-9][A-Za-z0-9@._-]{0,199}"
        )
    if session_id.endswith(".") or session_id.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError("Invalid session_id: reserved or filesystem-ambiguous name")
    return session_id


def _sniff_mime_magic(head: bytes) -> str | None:
    if not head:
        return None
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith(b"\x1f\x8b"):
        return "application/gzip"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "video/x-matroska"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "video/mp4"
    return None


def _encode_output_files(
    output_files: list,
    *,
    max_file_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> list[dict]:
    """Encode outputs within both per-file and aggregate budgets."""
    file_limit = _MAX_INLINE_FILE_BYTES if max_file_bytes is None else max_file_bytes
    total_limit = _MAX_INLINE_TOTAL_BYTES if max_total_bytes is None else max_total_bytes
    result: list[dict] = []
    total = 0
    for path in output_files:
        if not isinstance(path, str) or not path:
            continue
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            size = os.path.getsize(path)
            if size > file_limit or total + size > total_limit:
                continue
            with open(path, "rb") as handle:
                data = handle.read(file_limit + 1)
            if len(data) != size or len(data) > file_limit:
                continue
            digest = hashlib.sha256(data).hexdigest()
            mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if mime == "application/octet-stream":
                mime = _sniff_mime_magic(data[:12]) or mime
            result.append(
                {
                    "name": os.path.basename(path),
                    "content_base64": base64.b64encode(data).decode("ascii"),
                    "mime": mime,
                    "size": size,
                    "sha256": digest,
                }
            )
            total += size
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to inline output file %s: %s", path, exc)
    return result


def _output_omissions(
    output_files: list,
    encoded: list[dict],
    registered: dict[str, dict[str, Any]],
) -> list[dict]:
    included = {(entry.get("name"), entry.get("size"), entry.get("sha256")) for entry in encoded}
    omitted: list[dict] = []
    for path in output_files:
        if not isinstance(path, str) or not path:
            continue
        item: dict[str, Any] = {"name": os.path.basename(path), "path": path}
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                item.update(code="unavailable", error="output is missing, non-regular, or a symlink")
            else:
                size = os.path.getsize(path)
                digest = hashlib.sha256()
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                sha256 = digest.hexdigest()
                if (item["name"], size, sha256) in included:
                    continue
                registered_item = next(
                    (
                        metadata for metadata in registered.values()
                        if metadata.get("path") == os.path.realpath(path)
                    ),
                    None,
                )
                if registered_item:
                    item.update(registered_item)
                item.update(
                    size=size,
                    size_bytes=size,
                    sha256=sha256,
                    code="inline_budget_exceeded",
                    error="inline budget exceeded; fetch the authenticated download_url",
                )
        except Exception as exc:  # pylint: disable=broad-except
            item.update(code="read_failed", error=str(exc))
        omitted.append(item)
    return omitted


@dataclass
class SteeringEnvelope:
    steering_id: str
    message: str
    request_fingerprint: str
    manifest: dict[str, Any]
    state: str = "queued"
    queued_at: float = field(default_factory=time.time)
    consumed_at: float | None = None

    def status_dict(self) -> dict[str, Any]:
        return {
            "success": True,
            "steering_id": self.steering_id,
            "state": self.state,
            "queued_at": self.queued_at,
            "consumed_at": self.consumed_at,
        }


@dataclass
class Session:
    session_id: str
    workdir: str
    callback_url: str | None = None
    progress_webhook: str | None = None
    progress_logs: list[dict] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)
    status: str = "active"
    result: Optional[dict] = None
    callback_result: Optional[dict] = None
    output_files: dict[str, dict[str, Any]] = field(default_factory=dict)
    request_fingerprint: str | None = None
    request_manifest: dict[str, Any] = field(default_factory=dict)
    run_started: bool = False
    _callback_sent: bool = field(default=False, repr=False)
    _callback_pending: bool = field(default=False, repr=False)
    steering_messages: list[SteeringEnvelope] = field(default_factory=list)
    messages: Optional[list] = None
    event_sequence: int = 0
    callback_sequence: int = 0
    next_delivery_sequence: int = 1
    persistence_error: bool = field(default=False, repr=False, compare=False)
    delivery_condition: threading.Condition = field(
        default_factory=threading.Condition, repr=False, compare=False
    )


class SessionManager:
    def __init__(self, idle_timeout: int = 600):
        self.idle_timeout = idle_timeout
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.RLock()
        self._workdir_base = os.path.realpath(
            os.getenv("WORKDIR_BASE", "/storage/subagent_work")
        )
        self._state_dir = os.path.realpath(
            os.getenv("SUBAGENT_STATE_DIR", os.path.join(self._workdir_base, ".state"))
        )
        self._outbox_dir = os.path.join(self._state_dir, "outbox")
        self._deliveries_inflight: set[tuple[str, int, str]] = set()
        self._workdir_owners: dict[str, str] = {}
        self._blocked_session_ids: set[str] = set()
        self._load_state()
        self._recover_interrupted_sessions()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        self._outbox_thread = threading.Thread(target=self._outbox_loop, daemon=True)
        self._outbox_thread.start()

    def _state_path(self, session_id: str) -> str:
        return os.path.join(self._state_dir, f"{session_id}.json")

    @staticmethod
    def _atomic_json(path: str, value: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".state-", dir=os.path.dirname(path))
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

    def _persist_session_locked(self, session: Session) -> None:
        value = {
            "version": 1,
            "session_id": session.session_id,
            "workdir": session.workdir,
            "callback_url": session.callback_url,
            "progress_webhook": session.progress_webhook,
            "last_activity": session.last_activity,
            "status": session.status,
            "result": session.result,
            "callback_result": session.callback_result,
            "output_files": session.output_files,
            "request_fingerprint": session.request_fingerprint,
            "request_manifest": session.request_manifest,
            "run_started": session.run_started,
            "callback_sent": session._callback_sent,
            "callback_pending": session._callback_pending,
            "steering_messages": [asdict(item) for item in session.steering_messages],
            "messages": session.messages,
            "event_sequence": session.event_sequence,
            "callback_sequence": session.callback_sequence,
            "next_delivery_sequence": session.next_delivery_sequence,
        }
        try:
            self._atomic_json(self._state_path(session.session_id), value)
            session.persistence_error = False
        except Exception as exc:  # pylint: disable=broad-except
            session.persistence_error = True
            logger.error(
                "Failed to persist session state",
                extra={"session_id": session.session_id, "error": str(exc)},
            )
            raise SessionPersistenceError(
                f"Could not persist session {session.session_id}"
            ) from exc

    def _load_state(self) -> None:
        if not os.path.isdir(self._state_dir):
            return
        for filename in os.listdir(self._state_dir):
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(self._state_dir, filename), encoding="utf-8") as handle:
                    value = json.load(handle)
                session_id = validate_session_id(value.get("session_id"))
                expected_workdir = os.path.realpath(os.path.join(self._workdir_base, session_id))
                if os.path.realpath(value.get("workdir", "")) != expected_workdir:
                    raise ValueError("persisted workdir does not match canonical session path")
                steering = [SteeringEnvelope(**item) for item in value.get("steering_messages", [])]
                pending_callback = bool(value.get("callback_pending")) and not bool(value.get("callback_sent"))
                event_sequence = int(value.get("event_sequence", 0))
                callback_sequence = int(value.get("callback_sequence", 0))
                if pending_callback and callback_sequence <= 0:
                    callback_sequence = event_sequence
                next_delivery_sequence = int(value.get("next_delivery_sequence", 1))
                # Progress events are intentionally not durable. After a
                # process restart, let the durable completion advance even if
                # an earlier in-flight progress event vanished with the old
                # process.
                if pending_callback and callback_sequence:
                    next_delivery_sequence = callback_sequence
                session = Session(
                    session_id=session_id,
                    workdir=expected_workdir,
                    callback_url=value.get("callback_url"),
                    progress_webhook=value.get("progress_webhook"),
                    last_activity=float(value.get("last_activity", time.time())),
                    status=value.get("status", "active"),
                    result=value.get("result"),
                    callback_result=value.get("callback_result"),
                    output_files=value.get("output_files") or {},
                    request_fingerprint=value.get("request_fingerprint"),
                    request_manifest=value.get("request_manifest") or {},
                    run_started=bool(value.get("run_started")),
                    _callback_sent=bool(value.get("callback_sent")),
                    _callback_pending=bool(value.get("callback_pending")),
                    steering_messages=steering,
                    messages=value.get("messages"),
                    event_sequence=event_sequence,
                    callback_sequence=callback_sequence,
                    next_delivery_sequence=next_delivery_sequence,
                )
                filesystem_key = os.path.normcase(expected_workdir)
                owner = self._workdir_owners.get(filesystem_key)
                if owner is not None and owner != session_id:
                    raise ValueError("persisted session ids alias the same workdir")
                self._workdir_owners[filesystem_key] = session_id
                self._sessions[session_id] = session
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Ignoring invalid persisted session state", extra={"file": filename, "error": str(exc)})
                candidate = os.path.splitext(filename)[0]
                try:
                    self._blocked_session_ids.add(validate_session_id(candidate))
                except ValueError:
                    pass

    def _recover_interrupted_sessions(self) -> None:
        """Turn work lost to a process restart into a durable terminal result."""
        interrupted = [
            session.session_id
            for session in self._sessions.values()
            if session.status in {"active", "completing"}
        ]
        for session_id in interrupted:
            self.store_result(
                session_id,
                {
                    "session_id": session_id,
                    "success": False,
                    "report": "Subagent process restarted before this task completed; retry with a new session_id",
                    "output_files": [],
                    "processing_time_sec": 0,
                    "error_code": "interrupted_by_restart",
                },
            )

    def get_or_create(self, session_id: str) -> Session:
        session_id = validate_session_id(session_id)
        with self._lock:
            if session_id in self._blocked_session_ids:
                raise SessionPersistenceError(
                    f"Session {session_id} has unreadable durable state and cannot be reused"
                )
            existing = self._sessions.get(session_id)
            if existing is not None:
                existing.last_activity = time.time()
                return existing
            os.makedirs(self._workdir_base, exist_ok=True)
            if os.path.islink(self._workdir_base):
                raise ValueError("WORKDIR_BASE must not be a symlink")
            workdir = os.path.realpath(os.path.join(self._workdir_base, session_id))
            if os.path.commonpath((workdir, self._workdir_base)) != self._workdir_base:
                raise ValueError("Invalid session_id: resolves outside workdir base")
            if os.path.lexists(workdir) and os.path.islink(workdir):
                raise ValueError("Session workdir must not be a symlink")
            filesystem_key = os.path.normcase(workdir)
            owner = self._workdir_owners.get(filesystem_key)
            if owner is not None and owner != session_id:
                raise ValueError("Invalid session_id: aliases an existing session workdir")
            os.makedirs(workdir, exist_ok=True)
            session = Session(session_id=session_id, workdir=workdir)
            self._sessions[session_id] = session
            try:
                self._persist_session_locked(session)
            except SessionPersistenceError:
                self._sessions.pop(session_id, None)
                try:
                    os.rmdir(workdir)
                except OSError:
                    pass
                raise
            self._workdir_owners[filesystem_key] = session_id
            logger.info("Session created", extra={"session_id": session_id, "workdir": workdir})
            return session

    def begin_execution(self, session_id: str, fingerprint: str) -> tuple[Session, str]:
        """Atomically create/claim a request: ``new``, ``replay``, or ``conflict``."""
        with self._lock:
            session = self.get_or_create(session_id)
            if session.persistence_error:
                raise SessionPersistenceError(
                    f"Session {session_id} is blocked by an earlier persistence failure"
                )
            if session.request_fingerprint is None:
                session.request_fingerprint = fingerprint
                self._persist_session_locked(session)
                return session, "new"
            if session.request_fingerprint == fingerprint:
                return session, "replay"
            return session, "conflict"

    def mark_execution_started(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.run_started:
                return False
            session.run_started = True
            session.last_activity = time.time()
            self._persist_session_locked(session)
            return True

    def set_request_manifest(self, session_id: str, manifest: dict[str, Any]) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.request_manifest = manifest
                self._persist_session_locked(session)

    def get_session(self, session_id: str) -> Optional[Session]:
        try:
            session_id = validate_session_id(session_id)
        except ValueError:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = time.time()
            return session

    def try_begin_completion(self, session_id: str) -> bool:
        """Atomically close steering admission before accepting ``end_task``."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.status != "active":
                return False
            if any(item.state == "queued" for item in session.steering_messages):
                return False
            session.status = "completing"
            session.last_activity = time.time()
            self._persist_session_locked(session)
            return True

    def set_callback(self, session_id: str, callback_url: Optional[str], progress_webhook: Optional[str]) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.callback_url = callback_url
                session.progress_webhook = progress_webhook
                self._persist_session_locked(session)

    def _next_event_locked(self, session: Session, payload: dict[str, Any]) -> dict[str, Any]:
        session.event_sequence += 1
        event = {**payload, "sequence": session.event_sequence, "emitted_at": time.time()}
        self._persist_session_locked(session)
        return event

    def _register_output_files(
        self, session: Session, output_files: list
    ) -> dict[str, dict[str, Any]]:
        registered: dict[str, dict[str, Any]] = {}
        workdir = os.path.realpath(session.workdir)
        secret = (_WEBHOOK_TOKEN or "wazzapsubagent-output-id-v1").encode()
        for raw_path in output_files:
            if not isinstance(raw_path, str) or not raw_path:
                continue
            path = os.path.realpath(raw_path)
            try:
                if (
                    os.path.commonpath((path, workdir)) != workdir
                    or path == workdir
                    or os.path.islink(raw_path)
                    or not os.path.isfile(path)
                ):
                    continue
                digest = hashlib.sha256()
                size = 0
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        size += len(chunk)
                        digest.update(chunk)
                sha256 = digest.hexdigest()
                relative_path = os.path.relpath(path, workdir).replace(os.sep, "/")
                file_id = hmac.new(
                    secret,
                    f"{session.session_id}\0{relative_path}\0{size}\0{sha256}".encode(),
                    hashlib.sha256,
                ).hexdigest()[:40]
                mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
                metadata = {
                    "file_id": file_id,
                    "name": os.path.basename(path),
                    "path": path,
                    "size": size,
                    "size_bytes": size,
                    "sha256": sha256,
                    "mime": mime,
                    "download_url": f"/sessions/{session.session_id}/outputs/{file_id}",
                }
                registered[file_id] = metadata
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Could not register output download",
                    extra={"session_id": session.session_id, "path": raw_path, "error": str(exc)},
                )
        session.output_files = registered
        return registered

    def _build_delivery_result(self, session: Session, result: dict[str, Any]) -> dict[str, Any]:
        output_files = result.get("output_files") or []
        registered = self._register_output_files(session, output_files)
        encoded = _encode_output_files(output_files)
        # Preserve caller-provided inline data only for compatibility when no
        # file paths were declared; normal agent results are always rebuilt.
        if not output_files and isinstance(result.get("output_files_content"), list):
            encoded = result["output_files_content"]
        omissions = _output_omissions(output_files, encoded, registered)
        return {
            **result,
            "output_files_content": encoded,
            "output_files_omitted": omissions,
            "output_files_content_complete": not omissions,
        }

    def store_result(self, session_id: str, result: dict) -> None:
        callback: tuple[str, dict[str, Any]] | None = None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.status == "completed":
                return
            session.result = dict(result)
            session.callback_result = self._build_delivery_result(session, result)
            session.last_activity = time.time()
            session.status = "completed"
            if session.callback_url and not session._callback_sent and not session._callback_pending:
                session._callback_pending = True
                payload = self._next_event_locked(
                    session,
                    {
                        "type": "complete",
                        "session_id": session_id,
                        "result": session.callback_result,
                    },
                )
                session.callback_sequence = int(payload["sequence"])
                callback = (session.callback_url, payload)
            self._persist_session_locked(session)
        if callback:
            self._fire_webhook(*callback)

    def append_progress(self, session_id: str, entry: dict) -> None:
        callback: tuple[str, dict[str, Any]] | None = None
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.progress_logs.append(entry)
                session.last_activity = time.time()
                if session.progress_webhook:
                    callback = (
                        session.progress_webhook,
                        self._next_event_locked(
                            session,
                            {"type": "progress", "session_id": session_id, "entry": entry},
                        ),
                    )
        if callback:
            self._fire_webhook(*callback)

    def fire_queue_event(self, session_id: str, payload: dict) -> None:
        callback: tuple[str, dict[str, Any]] | None = None
        with self._lock:
            session = self._sessions.get(session_id)
            if session and session.progress_webhook:
                session.last_activity = time.time()
                callback = (session.progress_webhook, self._next_event_locked(session, payload))
        if callback:
            self._fire_webhook(*callback)

    def _outbox_path(self, payload: dict[str, Any]) -> str:
        return os.path.join(
            self._outbox_dir,
            f"{payload.get('session_id')}-{int(payload.get('sequence', 0)):020d}.json",
        )

    def _persist_outbox(self, url: str, payload: dict[str, Any]) -> str | None:
        if payload.get("type") != "complete":
            return None
        path = self._outbox_path(payload)
        self._atomic_json(path, {"url": url, "payload": payload})
        return path

    def _mark_delivery_success(self, payload: dict[str, Any], outbox_path: str | None) -> None:
        if outbox_path:
            try:
                os.unlink(outbox_path)
            except FileNotFoundError:
                pass
        if payload.get("type") == "complete":
            with self._lock:
                session = self._sessions.get(payload.get("session_id"))
                if session:
                    session._callback_sent = True
                    session._callback_pending = False
                    self._persist_session_locked(session)

    def _advance_delivery(self, session_id: str, sequence: int) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            return
        with session.delivery_condition:
            if sequence >= session.next_delivery_sequence:
                session.next_delivery_sequence = sequence + 1
            session.delivery_condition.notify_all()
        with self._lock:
            self._persist_session_locked(session)

    def _fire_webhook(self, url: str, payload: dict) -> None:
        """Persist completion before send; retry without claiming premature success."""
        try:
            outbox_path = self._persist_outbox(url, payload)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "Webhook not sent because its durable outbox write failed",
                extra={"url": url, "error": str(exc), "session_id": payload.get("session_id")},
            )
            return
        max_attempts = _WEBHOOK_RETRY_MAX
        delivery_key = (
            str(payload.get("session_id", "")),
            int(payload.get("sequence", 0)),
            str(payload.get("type", "")),
        )
        with self._lock:
            if delivery_key in self._deliveries_inflight:
                return
            self._deliveries_inflight.add(delivery_key)

        def _send() -> None:
            session_id = str(payload.get("session_id", ""))
            sequence = int(payload.get("sequence", 0))
            with self._lock:
                session = self._sessions.get(session_id)
            if session and sequence:
                with session.delivery_condition:
                    while sequence > session.next_delivery_sequence:
                        session.delivery_condition.wait(timeout=30)

            payload_to_send = payload
            stripped_on_413 = False
            attempt = 0
            success = False
            while attempt < max_attempts:
                attempt += 1
                try:
                    kwargs: dict[str, Any] = {"json": payload_to_send, "timeout": 30}
                    if _WEBHOOK_TOKEN:
                        kwargs["headers"] = {"X-Subagent-Webhook-Token": _WEBHOOK_TOKEN}
                    response = requests.post(url, **kwargs)
                    if response.status_code == 413 and not stripped_on_413:
                        stripped_on_413 = True
                        result_dict = payload_to_send.get("result") or {}
                        inline = result_dict.get("output_files_content") or []
                        with self._lock:
                            delivery_session = self._sessions.get(session_id)
                            registry = list(delivery_session.output_files.values()) if delivery_session else []
                        dropped = []
                        for item in inline:
                            if not isinstance(item, dict):
                                continue
                            metadata = next(
                                (
                                    candidate for candidate in registry
                                    if candidate.get("sha256") == item.get("sha256")
                                    and candidate.get("size_bytes") == item.get("size")
                                ),
                                {},
                            )
                            dropped.append({
                                **metadata,
                                "name": item.get("name", "unknown"),
                                "size": item.get("size"),
                                "size_bytes": item.get("size"),
                                "sha256": item.get("sha256"),
                                "mime": item.get("mime") or metadata.get("mime"),
                                "code": "callback_body_rejected",
                                "error": "inline content removed after HTTP 413; use download_url",
                            })
                        stripped_result = {
                            key: value for key, value in result_dict.items()
                            if key != "output_files_content"
                        }
                        stripped_result["output_files_omitted"] = list(
                            stripped_result.get("output_files_omitted") or []
                        ) + dropped
                        stripped_result["output_files_content_dropped"] = True
                        stripped_result["output_files_content_complete"] = False
                        payload_to_send = {**payload_to_send, "result": stripped_result}
                        attempt = 0
                        continue
                    response.raise_for_status()
                    success = True
                    self._mark_delivery_success(payload, outbox_path)
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    if attempt >= max_attempts:
                        logger.error(
                            "Webhook remains in durable outbox after retries",
                            extra={"url": url, "error": str(exc), "session_id": session_id},
                        )
                        break
                    time.sleep(min(_WEBHOOK_RETRY_MAX_BACKOFF, _WEBHOOK_RETRY_BASE_BACKOFF * (2 ** (attempt - 1))))
            # Do not let one permanently failing event deadlock later events.
            # Sequence numbers let the receiver reject/reconcile any late send.
            try:
                self._advance_delivery(session_id, sequence)
                if not success and payload.get("type") != "complete" and outbox_path:
                    try:
                        os.unlink(outbox_path)
                    except FileNotFoundError:
                        pass
            finally:
                with self._lock:
                    self._deliveries_inflight.discard(delivery_key)

        threading.Thread(target=_send, daemon=True).start()

    def _outbox_loop(self) -> None:
        while True:
            time.sleep(max(1.0, _OUTBOX_RETRY_INTERVAL))
            with self._lock:
                pending = [
                    (
                        session.callback_url,
                        {
                            "type": "complete",
                            "session_id": session.session_id,
                            "result": session.callback_result,
                            "sequence": session.callback_sequence or session.event_sequence,
                        },
                    )
                    for session in self._sessions.values()
                    if session.callback_url
                    and session.callback_result is not None
                    and session._callback_pending
                    and not session._callback_sent
                ]
            for url, payload in pending:
                self._fire_webhook(url, payload)
            if not os.path.isdir(self._outbox_dir):
                continue
            for filename in sorted(os.listdir(self._outbox_dir)):
                path = os.path.join(self._outbox_dir, filename)
                try:
                    with open(path, encoding="utf-8") as handle:
                        item = json.load(handle)
                    payload = item["payload"]
                    session_id = payload.get("session_id")
                    with self._lock:
                        session = self._sessions.get(session_id)
                        if session and session._callback_sent:
                            os.unlink(path)
                            continue
                    # _fire_webhook atomically rewrites the same durable path.
                    self._fire_webhook(item["url"], payload)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error("Could not retry durable outbox item", extra={"file": filename, "error": str(exc)})

    @staticmethod
    def check_webhook_health(webhook_url: str) -> bool:
        if not webhook_url:
            return False
        try:
            from urllib.parse import urlsplit, urlunsplit
            parsed = urlsplit(webhook_url)
            health_url = urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))
        except Exception:
            return False
        for attempt in range(1, _WEBHOOK_HEALTH_CHECK_ATTEMPTS + 1):
            try:
                if requests.get(health_url, timeout=_WEBHOOK_HEALTH_CHECK_TIMEOUT).status_code == 200:
                    return True
            except Exception:  # pylint: disable=broad-except
                pass
            if attempt < _WEBHOOK_HEALTH_CHECK_ATTEMPTS:
                time.sleep(1)
        return False

    def queue_steering(
        self,
        session_id: str,
        steering_id: str,
        message: str,
        request_fingerprint: str,
        manifest: dict[str, Any],
    ) -> tuple[SteeringEnvelope | None, str]:
        steering_id = validate_session_id(steering_id)
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.status != "active":
                return None, "inactive"
            for item in session.steering_messages:
                if item.steering_id == steering_id:
                    return item, "replay" if item.request_fingerprint == request_fingerprint else "conflict"
            envelope = SteeringEnvelope(
                steering_id=steering_id,
                message=message,
                request_fingerprint=request_fingerprint,
                manifest=manifest,
            )
            session.steering_messages.append(envelope)
            session.last_activity = time.time()
            self._persist_session_locked(session)
            return envelope, "new"

    def lookup_steering(
        self, session_id: str, steering_id: str
    ) -> SteeringEnvelope | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            for item in session.steering_messages:
                if item.steering_id == steering_id:
                    return item
            return None

    def add_steering_message(self, session_id: str, message: str) -> bool:
        steering_id = f"steer-{hashlib.sha256(f'{time.time_ns()}:{message}'.encode()).hexdigest()[:24]}"
        envelope, state = self.queue_steering(
            session_id,
            steering_id,
            message,
            hashlib.sha256(message.encode()).hexdigest(),
            {},
        )
        return envelope is not None and state in {"new", "replay"}

    def consume_steering_messages(self, session_id: str) -> list[str]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            messages: list[str] = []
            now = time.time()
            for item in session.steering_messages:
                if item.state == "queued":
                    item.state = "consumed"
                    item.consumed_at = now
                    messages.append(item.message)
            if messages:
                session.last_activity = now
                self._persist_session_locked(session)
            return messages

    def get_steering_status(self, session_id: str, steering_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            for item in session.steering_messages:
                if item.steering_id == steering_id:
                    return {"session_id": session_id, **item.status_dict()}
            return None

    def store_messages(self, session_id: str, messages: list) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.messages = messages
                session.last_activity = time.time()
                self._persist_session_locked(session)

    def get_messages(self, session_id: str) -> Optional[list]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.messages is None:
                return None
            return list(session.messages)

    def get_result(self, session_id: str, *, delivery: bool = False) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = time.time()
                return session.callback_result if delivery else session.result
            return None

    def open_output_file(
        self, session_id: str, file_id: str
    ) -> tuple[Any, dict[str, Any]] | None:
        """Open a registered output by descriptor, resisting symlink races."""
        with self._lock:
            session = self._sessions.get(session_id)
            metadata = dict(session.output_files.get(file_id) or {}) if session else {}
            workdir = session.workdir if session else ""
            if session:
                session.last_activity = time.time()
        if not metadata:
            return None
        path = metadata.get("path")
        if not isinstance(path, str) or not path:
            return None
        real_path = os.path.realpath(path)
        real_workdir = os.path.realpath(workdir)
        try:
            if (
                os.path.commonpath((real_path, real_workdir)) != real_workdir
                or real_path == real_workdir
                or os.path.islink(path)
            ):
                return None
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size != metadata.get("size_bytes"):
                os.close(descriptor)
                return None
            handle = os.fdopen(descriptor, "rb")
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            if digest.hexdigest() != metadata.get("sha256"):
                handle.close()
                return None
            handle.seek(0)
            return handle, metadata
        except (OSError, ValueError):
            return None

    def cleanup_session(self, session_id: str) -> None:
        try:
            session_id = validate_session_id(session_id)
        except ValueError:
            return
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            return
        expected = os.path.realpath(os.path.join(self._workdir_base, session_id))
        if session.workdir == expected and os.path.isdir(expected) and not os.path.islink(expected):
            try:
                shutil.rmtree(expected)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "Session cleanup retained state because workdir removal failed",
                    extra={"session_id": session_id, "error": str(exc)},
                )
                return
        try:
            os.unlink(self._state_path(session_id))
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.error(
                "Session cleanup retained ownership because state removal failed",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return
        if os.path.isdir(self._outbox_dir):
            prefix = f"{session_id}-"
            for filename in os.listdir(self._outbox_dir):
                if filename.startswith(prefix) and filename.endswith(".json"):
                    try:
                        os.unlink(os.path.join(self._outbox_dir, filename))
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        logger.error(
                            "Session cleanup retained ownership because outbox removal failed",
                            extra={"session_id": session_id, "error": str(exc)},
                        )
                        return
        with self._lock:
            if self._sessions.get(session_id) is session:
                self._sessions.pop(session_id, None)
                self._workdir_owners.pop(os.path.normcase(expected), None)

    def _cleanup_loop(self) -> None:
        while True:
            time.sleep(10)
            now = time.time()
            with self._lock:
                to_remove = [
                    sid for sid, session in self._sessions.items()
                    if now - session.last_activity > self.idle_timeout
                    and session.status == "completed"
                    and (session._callback_sent or not session.callback_url)
                ]
            for session_id in to_remove:
                self.cleanup_session(session_id)
