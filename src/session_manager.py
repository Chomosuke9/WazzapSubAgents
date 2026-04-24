import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Session:
    session_id: str
    workdir: str
    last_activity: float = field(default_factory=time.time)
    status: str = "active"
    result: Optional[dict] = None


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

    def store_result(self, session_id: str, result: dict) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.result = result
                session.last_activity = time.time()
                session.status = "completed"
                logger.info("Result stored", extra={"session_id": session_id})

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
