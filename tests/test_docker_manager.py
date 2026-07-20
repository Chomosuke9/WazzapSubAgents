from unittest.mock import MagicMock, patch

import pytest
from docker.errors import DockerException, ImageNotFound

from src.docker_manager import DockerManager


class TestDockerManagerInit:
    def test_init_success(self, mock_docker_client):
        dm = DockerManager()
        assert dm.image_name == "executor-service:v1.0.0"

    def test_init_hard_error_if_docker_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "docker.DockerClient",
            lambda **kwargs: (_ for _ in ()).throw(DockerException("no docker")),
        )
        with pytest.raises(RuntimeError, match="Docker daemon not available"):
            DockerManager()

    def test_project_root_points_at_repository(self, mock_docker_client):
        dm = DockerManager()
        assert (dm.project_root / "src" / "docker_manager.py").is_file()


class TestImageExists:
    def test_image_exists_true(self, mock_docker_client):
        dm = DockerManager()
        assert dm.image_exists() is True
        mock_docker_client.images.get.assert_called_once_with("executor-service:v1.0.0")

    def test_image_exists_false(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = ImageNotFound("not found")
        dm = DockerManager()
        assert dm.image_exists() is False

    def test_image_is_current_checks_source_label(self, mock_docker_client, monkeypatch):
        image = MagicMock()
        image.attrs = {
            "Config": {
                "Labels": {
                    DockerManager.SOURCE_LABEL: "current-hash",
                },
            },
        }
        mock_docker_client.images.get.return_value = image
        dm = DockerManager()
        monkeypatch.setattr(dm, "source_fingerprint", lambda: "current-hash")
        assert dm.image_is_current() is True

    def test_image_without_source_label_is_stale(self, mock_docker_client):
        image = MagicMock()
        image.attrs = {"Config": {"Labels": {}}}
        mock_docker_client.images.get.return_value = image
        dm = DockerManager()
        assert dm.image_is_current() is False


class TestContainerRunning:
    def test_container_running_true(self, mock_docker_client):
        container = MagicMock()
        container.status = "running"
        mock_docker_client.containers.get.return_value = container
        dm = DockerManager()
        assert dm.container_running() is True

    def test_container_running_false(self, mock_docker_client):
        import docker.errors
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
        dm = DockerManager()
        assert dm.container_running() is False

    def test_container_image_identity_is_checked(self, mock_docker_client):
        container = MagicMock()
        container.image.id = "sha256:new"
        image = MagicMock()
        image.id = "sha256:new"
        mock_docker_client.containers.get.return_value = container
        mock_docker_client.images.get.return_value = image
        dm = DockerManager()
        assert dm.container_uses_current_image() is True


class TestBuildImage:
    @patch("src.docker_manager.subprocess.run")
    def test_build_image_success(self, mock_run, mock_docker_client):
        mock_run.return_value = MagicMock()
        dm = DockerManager()
        dm.build_image()
        mock_run.assert_called_once()

    @patch("src.docker_manager.subprocess.run")
    def test_build_image_failure(self, mock_run, mock_docker_client):
        mock_run.side_effect = Exception("build failed")
        dm = DockerManager()
        with pytest.raises(Exception):
            dm.build_image()
