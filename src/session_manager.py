import base64
import mimetypes
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import requests

from src.logger import get_logger

logger = get_logger(__name__)

# Webhook delivery tunables. The WazzapAgents webhook server is always-on
# (auto-restarts on crash), so transient failures are expected to resolve
# quickly. We retry aggressively with exponential backoff to match that
# reliability guarantee.
_WEBHOOK_RETRY_MAX = int(os.getenv("WEBHOOK_RETRY_MAX", "10"))
_WEBHOOK_RETRY_BASE_BACKOFF = float(os.getenv("WEBHOOK_RETRY_BASE_BACKOFF", "0.5"))
_WEBHOOK_RETRY_MAX_BACKOFF = float(os.getenv("WEBHOOK_RETRY_MAX_BACKOFF", "30.0"))

# Pre-flight health check: how many times to probe the webhook endpoint
# before giving up. Used by ``check_webhook_health`` to confirm the
# WazzapAgents bridge is reachable before submitting a task.
_WEBHOOK_HEALTH_CHECK_ATTEMPTS = int(os.getenv("WEBHOOK_HEALTH_CHECK_ATTEMPTS", "3"))
_WEBHOOK_HEALTH_CHECK_TIMEOUT = float(os.getenv("WEBHOOK_HEALTH_CHECK_TIMEOUT", "5.0"))

# Maximum file size (bytes) to inline as base64 in the webhook callback
# for cross-machine deployments. Matches SUBAGENT_MAX_INLINE_FILE_BYTES
# in WazzapAgents. Override via SUBAGENT_MAX_INLINE_FILE_BYTES env var.
_MAX_INLINE_FILE_BYTES = int(os.getenv("SUBAGENT_MAX_INLINE_FILE_BYTES", str(50 * 1024 * 1024)))


def _encode_output_files(output_files: list) -> list[dict]:
    """Encode output_files as base64 for cross-machine webhook delivery.

    Returns a list of {name, content_base64, mime} dicts for files that:
    - exist and are regular files
    - have size <= _MAX_INLINE_FILE_BYTES

    Files missing, not regular, or too large are silently omitted
    (they remain in output_files as paths for single-machine fallback).

    MIME detection uses mimetypes.guess_type plus a first-pass magic-byte
    sniff for files with absent or misleading extensions. The Agents side
    (output.py) does more thorough detection on the written file; this sniff
    improves cross-machine accuracy before the file is base64-encoded.
    """
    result = []
    for path in output_files:
        if not isinstance(path, str) or not path:
            continue
        try:
            if not os.path.isfile(path):
                continue
            size = os.path.getsize(path)
            if size > _MAX_INLINE_FILE_BYTES:
                logger.info(
                    "omitting %s from output_files_content: size %d bytes exceeds inline limit %d",
                    os.path.basename(path),
                    size,
                    _MAX_INLINE_FILE_BYTES,
                    extra={"path": path},
                )
                continue
            with open(path, "rb") as fh:
                data = fh.read()
            mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
            # First-pass magic-byte sniff: improves MIME accuracy for files
            # with absent or misleading extensions in cross-machine mode.
            if mime == "application/octet-stream" or mime is None:
                head = data[:12] if len(data) >= 12 else data
                sniffed = _sniff_mime_magic(head)
                if sniffed:
                    mime = sniffed
            result.append({
                "name": os.path.basename(path),
                "content_base64": base64.b64encode(data).decode("ascii"),
                "mime": mime,
            })
        except Exception as exc:
            logger.warning(
                "Failed to inline output file %s: %s",
                path,
                exc,
                extra={"path": path},
            )
    return result


def _sniff_mime_magic(head: bytes) -> str | None:
    """Lightweight magic-byte sniff for common file types.

    Returns a MIME type string if recognized, or None if unknown.
    Only called when mimetypes.guess_type yields application/octet-stream
    or None; this is a first-pass improvement for cross-machine accuracy.
    """
    if not head:
        return None
    if head.startswith(b'%PDF-'):
        return 'application/pdf'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if head.startswith(b'GIF87a') or head.startswith(b'GIF89a'):
        return 'image/gif'
    if len(head) >= 12 and head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    if head.startswith(b'PK\x03\x04'):
        return 'application/zip'
    if head.startswith(b'\x1f\x8b'):
        return 'application/gzip'
    if head.startswith(b'\x1aE\xdf\xa3'):
        return 'video/x-matroska'
    if len(head) >= 8 and head[4:8] == b'ftyp':
        return 'video/mp4'
    return None


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
    _callback_sent: bool = field(default=False, repr=False)
    steering_messages: list[str] = field(default_factory=list)
    messages: Optional[list] = None


class SessionManager:
    def __init__(self, idle_timeout: int = 600):
        self.idle_timeout = idle_timeout
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.RLock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def get_or_create(self, session_id: str) -> Session:
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_activity = time.time()
                return session            # WORKDIR_BASE must match the executor sidecar so files written by
            # bash/python tools land in the same place we collect output_files
            # from. Defaults to /tmp/work for backwards compatibility, but
            # docker-compose overrides it to a host-shared path so WazzapAgents
            # can read the resulting files.
            workdir_base = os.getenv("WORKDIR_BASE", "/storage/subagent_work")
            # `session_id` is taken straight from the HTTP request body
            # (src/app.py) with no content validation, and
            # `cleanup_session` later runs `shutil.rmtree(session.workdir)`.
            # Without sanitization a caller could pass:
            #   - ``"/etc"``       → `os.path.join` discards `workdir_base`
            #     and rmtree's `/etc`.
            #   - ``"../../etc"``  → `realpath` resolves outside
            #     `workdir_base` and rmtree's that target instead.
            # Strip leading separators, resolve to an absolute path, and
            # require the result to live strictly inside `workdir_base`.
            safe_session_id = session_id.lstrip(os.sep)
            real_base = os.path.realpath(workdir_base)
            workdir = os.path.realpath(os.path.join(real_base, safe_session_id))
            if workdir != real_base and not workdir.startswith(real_base + os.sep):
                raise ValueError(
                    f"Invalid session_id {session_id!r}: resolves outside workdir_base"
                )
            if workdir == real_base:
                # An empty / dot-only session_id would alias the base dir;
                # cleanup would then delete the whole workdir tree.
                raise ValueError(
                    f"Invalid session_id {session_id!r}: must not be empty"
                )
            os.makedirs(workdir, exist_ok=True)
            session = Session(session_id=session_id, workdir=workdir)
            self._sessions[session_id] = session
            logger.info("Session created", extra={"session_id": session_id, "workdir": workdir})
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return an existing session without creating one.

        Used by ``/steer`` to reach the running session's ``workdir`` so
        steered input files can be staged into it. Unlike
        :meth:`get_or_create`, a missing session yields ``None`` instead of
        materialising a new workdir for a session that was never submitted.
        """
        with self._lock:
            return self._sessions.get(session_id)

    def set_callback(self, session_id: str, callback_url: Optional[str], progress_webhook: Optional[str]) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.callback_url = callback_url
                session.progress_webhook = progress_webhook
                logger.info("Callback URLs set", extra={"session_id": session_id, "callback_url": callback_url, "progress_webhook": progress_webhook})

    def store_result(self, session_id: str, result: dict) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.result = result
                session.last_activity = time.time()
                session.status = "completed"
                logger.info("Result stored", extra={"session_id": session_id})
                if session.callback_url and not session._callback_sent:
                    session._callback_sent = True
                    output_files = result.get("output_files") or []
                    output_files_content = _encode_output_files(output_files)
                    payload = {
                        "type": "complete",
                        "session_id": session_id,
                        "result": {
                            **result,
                            "output_files_content": output_files_content,
                        },
                    }
                    self._fire_webhook(session.callback_url, payload)

    def append_progress(self, session_id: str, entry: dict) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.progress_logs.append(entry)
                session.last_activity = time.time()
                if session.progress_webhook:
                    payload = {
                        "type": "progress",
                        "session_id": session_id,
                        "entry": entry,
                    }
                    self._fire_webhook(session.progress_webhook, payload)

    def fire_queue_event(self, session_id: str, payload: dict) -> None:
        """Fire an out-of-band queue-status webhook (``queued`` /
        ``queue_advanced``) to the session's configured progress webhook.

        This is used by :class:`src.concurrency.SubAgentQueue` to notify
        the bridge (and ultimately the end user) about a session's
        position in the global FIFO queue. Unlike :meth:`append_progress`
        we do NOT touch ``progress_logs`` — queue state is external
        scheduling information, not sub-agent progress.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or not session.progress_webhook:
                return
            url = session.progress_webhook
        self._fire_webhook(url, payload)

    def _fire_webhook(self, url: str, payload: dict) -> None:
        """Fire a webhook with aggressive retries.

        The WazzapAgents webhook server is always-on and auto-restarts
        on crash, so transient 5xx / connection-refused errors are
        expected to heal quickly. We retry with exponential backoff
        starting from a short 0.5 s base and cap at 30 s, defaulting
        to 10 attempts (up from 5) to match the always-on guarantee.
        """
        max_attempts = _WEBHOOK_RETRY_MAX
        base_backoff = _WEBHOOK_RETRY_BASE_BACKOFF
        max_backoff = _WEBHOOK_RETRY_MAX_BACKOFF

        def _send():
            payload_to_send = payload
            stripped_on_413 = False
            attempt = 0
            while attempt < max_attempts:
                attempt += 1
                try:
                    response = requests.post(url, json=payload_to_send, timeout=30)
                    if response.status_code == 413 and not stripped_on_413:
                        stripped_on_413 = True
                        result_dict = payload_to_send.get("result") or {}
                        stripped_result = {k: v for k, v in result_dict.items() if k != "output_files_content"}
                        stripped_result["output_files_content_dropped"] = True
                        payload_to_send = {**payload_to_send, "result": stripped_result}
                        logger.warning(
                            "Webhook 413: stripping output_files_content and retrying from attempt 1",
                            extra={"url": url, "attempt": attempt},
                        )
                        # Reset to 0 (not 1) because the while loop increments at the top,
                        # so the stripped payload will start at attempt 1 on the next iteration.
                        attempt = 0
                        continue
                    if response.status_code == 413 and stripped_on_413:
                        logger.warning(
                            "Webhook 413 after strip: payload already stripped, retrying with backoff",
                            extra={"url": url, "attempt": attempt},
                        )
                    response.raise_for_status()
                    logger.info(
                        "Webhook sent",
                        extra={"url": url, "status_code": response.status_code, "attempt": attempt},
                    )
                    return
                except Exception as e:
                    if attempt >= max_attempts:
                        logger.error(
                            "Webhook failed permanently after %d attempts",
                            max_attempts,
                            extra={"url": url, "error": str(e)},
                        )
                        return
                    backoff = min(max_backoff, base_backoff * (2 ** (attempt - 1)))
                    logger.warning(
                        "Webhook failed; retrying",
                        extra={"url": url, "error": str(e), "attempt": attempt, "backoff_s": backoff},
                    )
                    time.sleep(backoff)

        threading.Thread(target=_send, daemon=True).start()

    @staticmethod
    def check_webhook_health(webhook_url: str) -> bool:
        """Probe the WazzapAgents webhook health endpoint.

        The bridge exposes ``GET /health`` on the same host/port as the
        callback endpoint. This pre-flight check confirms the always-on
        webhook server is reachable before we submit a task that relies
        on it for progress and completion callbacks.

        Returns ``True`` if the health check succeeds, ``False`` otherwise.
        """
        if not webhook_url:
            return False
        # Derive the health URL from the callback URL:
        #   http://host:8081/subagent/callback → http://host:8081/health
        try:
            from urllib.parse import urlsplit, urlunsplit
            parsed = urlsplit(webhook_url)
            health_url = urlunsplit((
                parsed.scheme,
                parsed.netloc,
                "/health",
                "",
                "",
            ))
        except Exception:
            return False

        for attempt in range(1, _WEBHOOK_HEALTH_CHECK_ATTEMPTS + 1):
            try:
                resp = requests.get(health_url, timeout=_WEBHOOK_HEALTH_CHECK_TIMEOUT)
                if resp.status_code == 200:
                    logger.info(
                        "Webhook health check passed",
                        extra={"health_url": health_url, "attempt": attempt},
                    )
                    return True
                logger.warning(
                    "Webhook health check returned %d",
                    resp.status_code,
                    extra={"health_url": health_url, "attempt": attempt},
                )
            except Exception as e:
                logger.warning(
                    "Webhook health check failed",
                    extra={"health_url": health_url, "attempt": attempt, "error": str(e)},
                )
            if attempt < _WEBHOOK_HEALTH_CHECK_ATTEMPTS:
                time.sleep(1.0)
        logger.error(
            "Webhook health check failed after %d attempts",
            _WEBHOOK_HEALTH_CHECK_ATTEMPTS,
            extra={"health_url": health_url},
        )
        return False

    def add_steering_message(self, session_id: str, message: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.status != "active":
                return False
            session.steering_messages.append(message)
            session.last_activity = time.time()
            logger.info(
                "Steering message added",
                extra={"session_id": session_id, "message_preview": message[:200]},
            )
            return True

    def consume_steering_messages(self, session_id: str) -> list[str]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            messages = list(session.steering_messages)
            session.steering_messages.clear()
            if messages:
                logger.info(
                    "Steering messages consumed by agent",
                    extra={"session_id": session_id, "count": len(messages)},
                )
            return messages

    def store_messages(self, session_id: str, messages: list) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning(
                    "Cannot store messages: session not found",
                    extra={"session_id": session_id},
                )
                return
            session.messages = messages
            session.last_activity = time.time()
            logger.info(
                "Messages stored",
                extra={"session_id": session_id, "message_count": len(messages)},
            )

    def get_messages(self, session_id: str) -> Optional[list]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.messages is None:
                return None
            return list(session.messages)

    def get_result(self, session_id: str) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = time.time()
                return session.result
            return None

    def cleanup_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                if os.path.exists(session.workdir):
                    try:
                        shutil.rmtree(session.workdir)
                    except Exception as e:
                        logger.warning("Failed to remove workdir", extra={"session_id": session_id, "error": str(e)})
                logger.info("Session cleaned up", extra={"session_id": session_id})

    def _cleanup_loop(self) -> None:
        while True:
            time.sleep(10)
            now = time.time()
            with self._lock:
                to_remove = [
                    sid
                    for sid, s in self._sessions.items()
                    if now - s.last_activity > self.idle_timeout and s.status == "completed"
                ]
            for sid in to_remove:
                self.cleanup_session(sid)
