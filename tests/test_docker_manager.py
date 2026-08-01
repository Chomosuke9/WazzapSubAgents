from unittest.mock import MagicMock, patch

import pytest
from docker.errors import DockerException, ImageNotFound

from src.docker_manager import DockerManager
from src.runtime_paths import PROJECT_ROOT


class TestDockerManagerInit:
    def test_init_success(self, mock_docker_client):
        dm = DockerManager()
        assert dm.image_name == "executor-service:v1.0.0"

    def test_init_hard_error_if_docker_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "docker.from_env",
            lambda: (_ for _ in ()).throw(DockerException("no docker")),
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


class TestStartContainer:
    def test_default_workdir_matches_session_manager(
        self, mock_docker_client, monkeypatch
    ):
        monkeypatch.delenv("WORKDIR_BASE", raising=False)
        dm = DockerManager()
        dm.start_container()

        kwargs = mock_docker_client.containers.run.call_args.kwargs
        expected = str((PROJECT_ROOT / ".runtime" / "subagent_work").resolve())
        assert kwargs["environment"]["WORKDIR_BASE"] == "/storage/subagent_work"
        assert kwargs["environment"]["METHODS_DIR"] == "/methods"
        assert kwargs["environment"]["DEPENDENCIES_DIR"] == "/dependencies"
        assert kwargs["volumes"][expected] == {
            "bind": "/storage/subagent_work",
            "mode": "rw",
        }
        skills = str(PROJECT_ROOT / "skills")
        methods = str(PROJECT_ROOT / "methods")
        dependencies = str(PROJECT_ROOT / "dependencies")
        assert kwargs["volumes"][skills] == {"bind": "/skills", "mode": "ro"}
        assert kwargs["volumes"][methods] == {"bind": "/methods", "mode": "rw"}
        assert kwargs["volumes"][dependencies] == {
            "bind": "/dependencies",
            "mode": "rw",
        }
        assert "command" not in kwargs
        assert str(PROJECT_ROOT / "src") not in kwargs["volumes"]
        assert str(PROJECT_ROOT / "main.py") not in kwargs["volumes"]

    def test_forwards_only_allowed_skill_env_and_host_gateway(
        self, mock_docker_client, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
        monkeypatch.setenv(
            "EXECUTOR_TOOL_ENV_PASSTHROUGH",
            "CUSTOM_SKILL_KEY,llm_api_key,EXECUTOR_BIND_HOST,NINEROUTER_KEY",
        )
        monkeypatch.setenv("CUSTOM_SKILL_KEY", "custom-value")
        monkeypatch.setenv("LLM_API_KEY", "must-not-leak")
        monkeypatch.setenv("EXECUTOR_BIND_HOST", "attacker-controlled")
        monkeypatch.setenv("NINEROUTER_KEY", "nine-value")

        dm = DockerManager()
        dm.start_container()

        kwargs = mock_docker_client.containers.run.call_args.kwargs
        environment = kwargs["environment"]
        assert environment["CUSTOM_SKILL_KEY"] == "custom-value"
        assert environment["NINEROUTER_KEY"] == "nine-value"
        assert "llm_api_key" not in environment
        assert environment["EXECUTOR_BIND_HOST"] == "0.0.0.0"
        assert environment["EXECUTOR_TOOL_ENV_PASSTHROUGH"] == (
            "CUSTOM_SKILL_KEY,NINEROUTER_KEY"
        )
        assert kwargs["extra_hosts"] == {
            "host.docker.internal": "host-gateway"
        }


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


def test_source_fingerprint_ignores_live_mounted_knowledge(mock_docker_client, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "methods").mkdir()
    (tmp_path / "dependencies").mkdir()
    (tmp_path / "src" / "executor_server.py").write_text("version = 1", encoding="utf-8")
    (tmp_path / "skills" / "SKILL.md").write_text("first", encoding="utf-8")
    (tmp_path / "methods" / "example.md").write_text("first", encoding="utf-8")
    (tmp_path / "dependencies" / "package.txt").write_text("first", encoding="utf-8")

    dm = DockerManager()
    dm.project_root = tmp_path
    initial = dm.source_fingerprint()
    (tmp_path / "skills" / "SKILL.md").write_text("second", encoding="utf-8")
    (tmp_path / "methods" / "example.md").write_text("second", encoding="utf-8")
    (tmp_path / "dependencies" / "package.txt").write_text("second", encoding="utf-8")
    assert dm.source_fingerprint() == initial

    (tmp_path / "src" / "executor_server.py").write_text("version = 2", encoding="utf-8")
    assert dm.source_fingerprint() != initial
