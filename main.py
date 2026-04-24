from src.docker_manager import DockerManager
from src.logger import get_logger
from src.app import create_app

logger = get_logger("main")


if __name__ == "__main__":
    docker_mgr = DockerManager()

    # 1. Check & build image if needed
    if not docker_mgr.image_exists():
        logger.info("Docker image not found, building...")
        docker_mgr.build_image()
        logger.info("Docker image built successfully")
    else:
        logger.info("Docker image already exists, skipping build")

    # 2. Start container if not already running
    if not docker_mgr.container_running():
        logger.info("Starting container...")
        docker_mgr.start_container()
        logger.info("Container started")
    else:
        logger.info("Container already running")

    # 3. Wait for container health check
    docker_mgr.wait_for_container_ready(timeout=30)

    # 4. Start Flask app (listen :5000)
    app = create_app(docker_mgr)
    logger.info("Starting Flask server on :5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
