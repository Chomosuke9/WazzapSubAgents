import time
from typing import Any, Dict

import requests

from src.logger import get_logger

logger = get_logger(__name__)


class ContainerClient:
    def __init__(self, base_url: str, timeout: int = 300, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.HTTPError as e:
                if 500 <= e.response.status_code < 600 and attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("Transient server error, retrying...", extra={"attempt": attempt, "wait": wait})
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

    def run_bash(self, command: str, session_id: str = "default") -> Dict[str, Any]:
        logger.info("Running bash in container", extra={"command": command[:200], "session_id": session_id})
        result = self._post("/bash", {"command": command, "session_id": session_id})
        logger.info("Bash completed", extra={"returncode": result.get("returncode"), "session_id": session_id})
        return result

    def run_python(self, code: str, session_id: str = "default") -> Dict[str, Any]:
        logger.info("Running python in container", extra={"code": code[:200], "session_id": session_id})
        result = self._post("/python", {"code": code, "session_id": session_id})
        logger.info("Python completed", extra={"session_id": session_id})
        return result

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
