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
                return session
            # WORKDIR_BASE must match the executor sidecar so files written by
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
                    payload = {
                        "type": "complete",
                        "session_id": session_id,
                        "result": result,
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
            for attempt in range(1, max_attempts + 1):
                try:
                    response = requests.post(url, json=payload, timeout=30)
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
