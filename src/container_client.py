import os
import threading
import time
from typing import Any, Dict, Optional, TYPE_CHECKING
import uuid

import requests

from src.logger import get_logger

if TYPE_CHECKING:
    from src.docker_manager import DockerManager

logger = get_logger(__name__)


class ContainerClient:
    def __init__(
        self,
        base_url: str,
        timeout: int = 300,
        max_retries: int = 3,
        docker_mgr: Optional["DockerManager"] = None,
        http_timeout_grace: Optional[float] = None,
        api_token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.docker_mgr = docker_mgr
        self.http_timeout_grace = (
            float(os.getenv("EXECUTOR_HTTP_TIMEOUT_GRACE", "5"))
            if http_timeout_grace is None else float(http_timeout_grace)
        )
        if self.http_timeout_grace < 1:
            raise ValueError("http_timeout_grace must be at least 1 second")
        self.api_token = (
            os.getenv("EXECUTOR_API_TOKEN", "").strip()
            if api_token is None else api_token.strip()
        )
        self._restart_lock = threading.Lock()

    def _restart_container(self) -> None:
        """Attempt to restart the executor container via DockerManager.

        This is a best-effort recovery: if the container process has crashed
        (e.g. OOM-killed), we try to bring it back before retrying the
        request.  The restart itself may fail (e.g. Docker daemon down) and
        that is acceptable — the caller will simply get a connection error.

        A threading lock ensures that concurrent callers do not race to
        restart the container simultaneously, which could kill a freshly
        started container that another thread is already using.
        """
        if self.docker_mgr is None:
            return
        with self._restart_lock:
            try:
                logger.warning("Container unreachable, attempting restart...")
                if not self.docker_mgr.container_running():
                    self.docker_mgr.start_container()
                    self.docker_mgr.wait_for_container_ready(timeout=30)
                    logger.info("Container restarted successfully")
                else:
                    # Container exists but may be unresponsive — just wait.
                    logger.info("Container still running, waiting for health...")
                    self.docker_mgr.wait_for_container_ready(timeout=15)
            except Exception as exc:
                logger.error("Container restart failed", extra={"error": str(exc)})

    def _post(self, endpoint: str, payload: Dict[str, Any], timeout: Optional[int] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        restarted = False
        # A stable id makes a retry safe even if the executor finished the
        # command but its HTTP response was lost. The sidecar caches the first
        # result for this id and never runs the command twice.
        payload = {**payload}
        payload.setdefault("request_id", uuid.uuid4().hex)
        request_timeout = (
            float(timeout) + self.http_timeout_grace
            if timeout is not None else self.timeout
        )
        for attempt in range(1, self.max_retries + 1):
            try:
                headers = (
                    {"Authorization": f"Bearer {self.api_token}"}
                    if self.api_token else None
                )
                resp = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=request_timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.HTTPError as e:
                if 500 <= e.response.status_code < 600 and attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("Transient server error, retrying...", extra={"attempt": attempt, "wait": wait})
                    time.sleep(wait)
                    continue
                raise
            except requests.exceptions.ConnectionError:
                # Container is likely down (OOM-killed, crashed, etc.).
                # Try to restart once before burning through remaining retries.
                if not restarted:
                    restarted = True
                    self._restart_container()
                    continue
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("Request failed, retrying...", extra={"attempt": attempt, "wait": wait})
                    time.sleep(wait)
                    continue
                raise
            except requests.exceptions.RequestException:
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("Request failed, retrying...", extra={"attempt": attempt, "wait": wait})
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"Failed to POST {url} after {self.max_retries} attempts")

    def run_bash(self, command: str, session_id: str = "default", timeout: Optional[int] = None) -> Dict[str, Any]:
        logger.info("Running bash in container", extra={"command": command[:200], "session_id": session_id, "timeout": timeout})
        result = self._post("/bash", {"command": command, "session_id": session_id, "timeout": timeout}, timeout=timeout)
        logger.info("Bash completed", extra={"returncode": result.get("returncode"), "session_id": session_id})
        return result

    def run_python(self, code: str, session_id: str = "default", timeout: Optional[int] = None) -> Dict[str, Any]:
        logger.info("Running python in container", extra={"code": code[:200], "session_id": session_id, "timeout": timeout})
        result = self._post("/python", {"code": code, "session_id": session_id, "timeout": timeout}, timeout=timeout)
        logger.info("Python completed", extra={"session_id": session_id})
        return result

    def run_javascript(self, code: str, session_id: str = "default", timeout: Optional[int] = None) -> Dict[str, Any]:
        logger.info("Running javascript in container", extra={"code": code[:200], "session_id": session_id, "timeout": timeout})
        result = self._post("/javascript", {"code": code, "session_id": session_id, "timeout": timeout}, timeout=timeout)
        logger.info("Javascript completed", extra={"session_id": session_id})
        return result

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
