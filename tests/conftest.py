import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_docker_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("docker.DockerClient", lambda **kwargs: client)
    return client
