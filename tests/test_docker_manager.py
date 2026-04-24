import sys
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
        with pytest.raises(SystemExit):
            DockerManager()


class TestImageExists:
    def test_image_exists_true(self, mock_docker_client):
        dm = DockerManager()
        assert dm.image_exists() is True
        mock_docker_client.images.get.assert_called_once_with("executor-service:v1.0.0")

    def test_image_exists_false(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = ImageNotFound("not found")
        dm = DockerManager()
        assert dm.image_exists() is False


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
