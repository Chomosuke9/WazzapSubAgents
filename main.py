import os
import time
from urllib.parse import urlsplit

from src.app import create_app
from src.config import config
from src.container_client import ContainerClient
from src.logger import get_logger

logger = get_logger("main")


def _executor_management_mode() -> str:
    mode = config["executor_management_mode"]
    if mode != "auto":
        return mode
    host = (urlsplit(config["container_executor_url"]).hostname or "").lower()
    return "managed" if host in {"localhost", "127.0.0.1", "::1"} else "external"


def _wait_for_external_executor(url: str, timeout: float = 30.0) -> None:
    client = ContainerClient(url, max_retries=1)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.health_check():
            logger.info("External executor is ready", extra={"url": url})
            return
        time.sleep(1)
    raise TimeoutError(f"Executor at {url} was not ready after {timeout:.0f}s")


def build_app():
    """Build the main service with either a managed or external executor.

    Docker Compose owns its sidecar and therefore uses ``external`` mode. A
    native host install can keep ``auto``/``managed`` and let DockerManager
    create the sidecar. This prevents the main Compose container from trying
    to create a duplicate executor through the Docker socket.
    """
    executor_url = config["container_executor_url"]
    mode = _executor_management_mode()
    docker_mgr = None

    if mode == "managed":
        from src.docker_manager import DockerManager

        docker_mgr = DockerManager(executor_url=executor_url)
        image_current = docker_mgr.image_is_current()
        running = docker_mgr.container_running()
        if not image_current:
            if running:
                logger.info("Executor source changed; replacing stale container")
                docker_mgr.stop_container()
                running = False
            docker_mgr.build_image()
        elif running and not docker_mgr.container_uses_current_image():
            logger.info("Executor container uses an older image; replacing it")
            docker_mgr.stop_container()
            running = False
        if not running:
            docker_mgr.start_container()
        docker_mgr.wait_for_container_ready(timeout=30)
    else:
        _wait_for_external_executor(executor_url)

    return create_app(docker_mgr=docker_mgr, container_url=executor_url)


if __name__ == "__main__":
    app = build_app()
    port = config["flask_port"]
    logger.info("Starting Flask server", extra={"port": port})
    app.run(host=os.getenv("SUBAGENT_BIND_HOST", "127.0.0.1"), port=port, debug=False)
