import os

from src.app import create_app
from src.config import config
from src.docker_manager import DockerManager
from src.logger import get_logger

logger = get_logger("main")


def build_app():
    """Run the API on the host and own exactly one Docker sandbox."""
    docker_mgr = DockerManager(container_port=config["executor_port"])
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

    return create_app(docker_mgr=docker_mgr)


if __name__ == "__main__":
    app = build_app()
    port = config["flask_port"]
    logger.info("Starting Flask server", extra={"port": port})
    app.run(host=os.getenv("SUBAGENT_BIND_HOST", "127.0.0.1"), port=port, debug=False)
