import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import docker
from docker.errors import APIError, DockerException, ImageNotFound

from src.logger import get_logger
from src.runtime_paths import PROJECT_ROOT, workdir_base
from src.tool_environment import parse_tool_env_passthrough

logger = get_logger(__name__)


class DockerManager:
    SOURCE_LABEL = "io.wazzapagents.executor-source-sha256"

    def __init__(
        self,
        image_name: str = "executor-service:v1.0.0",
        dockerfile_path: str = ".",
        container_name: str = "executor-executor",
        container_port: int = 5001,
        executor_url: Optional[str] = None,
    ):
        self.project_root = PROJECT_ROOT
        self.image_name = image_name
        self.dockerfile_path = str(
            self.project_root if dockerfile_path == "." else Path(dockerfile_path).resolve()
        )
        self.container_name = os.getenv("EXECUTOR_CONTAINER_NAME", container_name)
        self.container_port = container_port
        self.executor_url = (
            executor_url or f"http://127.0.0.1:{self.container_port}"
        ).rstrip("/")
        self.host_port = urlsplit(self.executor_url).port or self.container_port
        try:
            self.client = docker.DockerClient(base_url="unix://var/run/docker.sock")
            self.client.ping()
        except DockerException as e:
            logger.error("Docker daemon not available", extra={"error": str(e)})
            raise RuntimeError("Docker daemon not available") from e

    def source_fingerprint(self) -> str:
        """Hash executor source that is copied into the managed image.

        A fixed image tag alone is not enough: otherwise a source update keeps
        talking to an old sidecar until an operator manually rebuilds it.
        """
        digest = hashlib.sha256()
        roots = [
            self.project_root / "Dockerfile",
            self.project_root / "requirements.txt",
            self.project_root / "main.py",
            self.project_root / "src",
            self.project_root / "skills",
        ]
        files: list[Path] = []
        for root in roots:
            if root.is_file():
                files.append(root)
            elif root.is_dir():
                files.extend(
                    path for path in root.rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts
                )
        for path in sorted(files, key=lambda item: item.as_posix()):
            digest.update(path.relative_to(self.project_root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def image_exists(self) -> bool:
        try:
            self.client.images.get(self.image_name)
            return True
        except ImageNotFound:
            return False
        except APIError as e:
            logger.error("Docker API error checking image", extra={"error": str(e)})
            return False

    def image_is_current(self) -> bool:
        """Return whether the managed image matches the checked-out source."""
        try:
            image = self.client.images.get(self.image_name)
        except (ImageNotFound, APIError):
            return False
        labels = (image.attrs.get("Config") or {}).get("Labels") or {}
        return labels.get(self.SOURCE_LABEL) == self.source_fingerprint()

    def build_image(self) -> None:
        logger.info("Building Docker image...", extra={"image": self.image_name})
        fingerprint = self.source_fingerprint()
        try:
            subprocess.run(
                [
                    "docker", "build",
                    "--label", f"{self.SOURCE_LABEL}={fingerprint}",
                    "-t", self.image_name,
                    self.dockerfile_path,
                ],
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

    def container_uses_current_image(self) -> bool:
        """Return whether the named container uses the current tagged image."""
        try:
            container = self.client.containers.get(self.container_name)
            image = self.client.images.get(self.image_name)
            return container.image.id == image.id
        except (docker.errors.NotFound, ImageNotFound, APIError):
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

            # Native mode: the bridge writes to the same `WORKDIR_BASE`
            # path the executor sidecar reads from, so we MUST bind-mount
            # `WORKDIR_BASE` host→container at the identical path.
            # Otherwise:
            #   - SessionManager creates dirs at /tmp/work/<id> on the host,
            #   - the executor sidecar runs bash with cwd /tmp/work/<id>
            #     inside the container,
            # and unless those map to the same on-disk dir, output files
            # end up in the wrong place and `_collect_output_files()`
            # finds nothing.
            #
            # Mount only the per-session workdir tree. The main service copies
            # accepted inputs into each workdir, so the executor never needs
            # visibility into the parent's raw /storage staging tree.
            resolved_workdir_base = workdir_base()

            os.makedirs(resolved_workdir_base, exist_ok=True)
            volumes = {
                resolved_workdir_base: {
                    "bind": resolved_workdir_base,
                    "mode": "rw",
                },
            }

            # Project code and skills — read-only, agent must never modify these
            project_root = str(self.project_root)
            skills_dir = os.path.join(project_root, "skills")
            src_dir = os.path.join(project_root, "src")
            main_py = os.path.join(project_root, "main.py")

            if os.path.isdir(skills_dir):
                volumes[skills_dir] = {"bind": "/skills", "mode": "ro"}
            if os.path.isdir(src_dir):
                volumes[src_dir] = {"bind": "/app/src", "mode": "ro"}
            if os.path.isfile(main_py):
                volumes[main_py] = {"bind": "/app/main.py", "mode": "ro"}

            tool_env_names = parse_tool_env_passthrough()
            container_environment = {
                name: os.getenv(name, "") for name in tool_env_names
            }
            # Protected executor settings are applied last so even future
            # parser changes cannot let a passthrough value override them.
            container_environment.update({
                "FLASK_PORT": str(self.container_port),
                "WORKDIR_BASE": resolved_workdir_base,
                "EXECUTOR_REQUIRE_UID_ISOLATION": "1",
                "EXECUTOR_PARENT_UID": str(
                    os.getuid() if hasattr(os, "getuid") else 0
                ),
                "EXECUTOR_API_TOKEN": os.getenv("EXECUTOR_API_TOKEN", ""),
                "EXECUTOR_REQUIRE_AUTH": os.getenv("EXECUTOR_REQUIRE_AUTH", "1"),
                "EXECUTOR_BIND_HOST": "0.0.0.0",
                "EXECUTOR_TOOL_ENV_PASSTHROUGH": ",".join(tool_env_names),
            })

            self.client.containers.run(
                self.image_name,
                name=self.container_name,
                command=["python", "-m", "src.executor_server"],
                detach=True,
                ports={f"{self.container_port}/tcp": ("127.0.0.1", self.host_port)},
                environment=container_environment,
                volumes=volumes,
                network_mode="bridge",
                extra_hosts={"host.docker.internal": "host-gateway"},
                restart_policy={"Name": "unless-stopped"},
            )
            logger.info(
                "Container started",
                extra={
                    "container": self.container_name,
                    "workdir_base": resolved_workdir_base,
                    "volumes": list(volumes.keys()),
                },
            )
        except APIError as e:
            logger.error("Failed to start container", extra={"error": str(e)})
            raise

    def wait_for_container_ready(self, timeout: int = 30) -> None:
        import requests

        url = f"{self.get_container_url()}/health"
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
        return self.executor_url

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
