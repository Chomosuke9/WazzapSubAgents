import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import requests

from src.logger import get_logger

logger = get_logger(__name__)


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
            workdir = f"/tmp/work/{session_id}"
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

    def _fire_webhook(self, url: str, payload: dict) -> None:
        max_attempts = int(os.getenv("WEBHOOK_RETRY_MAX", "5"))
        base_backoff = float(os.getenv("WEBHOOK_RETRY_BASE_BACKOFF", "1.0"))
        max_backoff = float(os.getenv("WEBHOOK_RETRY_MAX_BACKOFF", "30.0"))

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
                            "Webhook failed permanently",
                            extra={"url": url, "error": str(e), "attempts": attempt},
                        )
                        return
                    backoff = min(max_backoff, base_backoff * (2 ** (attempt - 1)))
                    logger.warning(
                        "Webhook failed; retrying",
                        extra={"url": url, "error": str(e), "attempt": attempt, "backoff_s": backoff},
                    )
                    time.sleep(backoff)

        threading.Thread(target=_send, daemon=True).start()

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
