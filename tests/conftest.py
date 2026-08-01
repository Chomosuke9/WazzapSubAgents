import os
import tempfile
from unittest.mock import MagicMock

import pytest

# Import-time configuration validation happens while pytest collects modules,
# before fixtures run. Safe dummy values make a clean checkout testable without
# requiring a developer's real .env or credentials.
os.environ["LLM_API_KEY"] = "test-api-key"
os.environ["AGENT_MODEL"] = "test-model"
os.environ["EXECUTOR_REQUIRE_AUTH"] = "0"
os.environ["EXECUTOR_REQUIRE_UID_ISOLATION"] = "0"
os.environ["EXECUTOR_PARENT_UID"] = "0"
os.environ["SUBAGENT_REQUIRE_API_AUTH"] = "0"
os.environ["EXECUTOR_API_TOKEN"] = ""
os.environ["SUBAGENT_API_TOKEN"] = ""
os.environ["SUBAGENT_WEBHOOK_TOKEN"] = ""
os.environ["BRAVE_SEARCH_API_KEY"] = ""
os.environ["NINEROUTER_KEY"] = ""
os.environ["NINEROUTER_URL"] = ""


@pytest.fixture(autouse=True)
def isolated_persistent_state(tmp_path, monkeypatch):
    """Keep durable session/upload state isolated across tests and processes."""
    workdir = tmp_path / "subagent_work"
    monkeypatch.setenv("WORKDIR_BASE", str(workdir))
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(tmp_path / "state"))
    # Legacy path-staging tests create independent TemporaryDirectory siblings.
    # Keep them inside a bounded test-only root while production remains strict.
    monkeypatch.setenv("SUBAGENT_INPUT_SOURCE_ROOT", tempfile.gettempdir())
    monkeypatch.setenv("SUBAGENT_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SUBAGENT_REQUIRE_API_AUTH", "0")
    monkeypatch.setenv("SUBAGENT_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("EXECUTOR_REQUIRE_AUTH", "0")
    monkeypatch.setenv("EXECUTOR_BIND_HOST", "127.0.0.1")


@pytest.fixture
def mock_docker_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("docker.from_env", lambda: client)
    return client
