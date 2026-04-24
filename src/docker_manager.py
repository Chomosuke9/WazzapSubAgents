import subprocess
import time
import sys
from typing import Optional

import docker
from docker.errors import DockerException, ImageNotFound, APIError

from src.logger import get_logger

logger = get_logger(__name__)


class DockerManager:
    def __init__(
        self,
        image_name: str = "executor-service:v1.0.0",
        dockerfile_path: str = ".",
        container_name: str = "executor-executor",
        container_port: int = 5001,
    ):
        self.image_name = image_name
        self.dockerfile_path = dockerfile_path
        self.container_name = container_name
        self.container_port = container_port
        try:
            self.client = docker.DockerClient(base_url="unix://var/run/docker.sock")
            self.client.ping()
        except DockerException as e:
            logger.error("Docker daemon not available", extra={"error": str(e)})
            sys.exit(1)

    def image_exists(self) -> bool:
        try:
            self.client.images.get(self.image_name)
            return True
        except ImageNotFound:
            return False
        except APIError as e:
            logger.error("Docker API error checking image", extra={"error": str(e)})
            return False

    def build_image(self) -> None:
        logger.info("Building Docker image...", extra={"image": self.image_name})
        try:
            subprocess.run(
                ["docker", "build", "-t", self.image_name, self.dockerfile_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            logger.info("Docker image built successfully", extra={"image": self.image_name})
        except subprocess.CalledProcessError as e:
            logger.error("Docker build failed", extra={"output": e.output})
            raise

    def container_running(self) -> bool:
        try:
            container = self.client.containers.get(self.container_name)
            return container.status == "running"
        except docker.errors.NotFound:
            return False
        except APIError as e:
            logger.error("Docker API error checking container", extra={"error": str(e)})
            return False

    def start_container(self) -> None:
        logger.info("Starting executor container...", extra={"container": self.container_name})
        try:
            # Remove old container if exists but not running
            try:
                old = self.client.containers.get(self.container_name)
                old.remove(force=True)
            except docker.errors.NotFound:
                pass

            self.client.containers.run(
                self.image_name,
                name=self.container_name,
                command=["python", "-m", "src.executor_server"],
                detach=True,
                ports={f"{self.container_port}/tcp": self.container_port},
                environment={"FLASK_PORT": str(self.container_port), "WORKDIR_BASE": "/tmp/work"},
                volumes={
                    "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "ro"},
                    "/tmp/work": {"bind": "/tmp/work", "mode": "rw"},
                },
                network_mode="bridge",
            )
            logger.info("Container started", extra={"container": self.container_name})
        except APIError as e:
            logger.error("Failed to start container", extra={"error": str(e)})
            raise

    def wait_for_container_ready(self, timeout: int = 30) -> None:
        import requests

        url = f"http://localhost:{self.container_port}/health"
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    logger.info("Container is ready", extra={"url": url})
                    return
            except Exception:
                pass
            time.sleep(1)
        raise TimeoutError(f"Container not ready after {timeout}s")

    def get_container_url(self) -> str:
        return f"http://localhost:{self.container_port}"

    def stop_container(self) -> None:
        try:
            container = self.client.containers.get(self.container_name)
            container.stop(timeout=10)
            container.remove(force=True)
            logger.info("Container stopped and removed", extra={"container": self.container_name})
        except docker.errors.NotFound:
            pass
        except APIError as e:
            logger.error("Error stopping container", extra={"error": str(e)})
