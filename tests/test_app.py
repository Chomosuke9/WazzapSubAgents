from unittest.mock import MagicMock

import pytest

from src.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    docker_mgr = MagicMock()
    docker_mgr.get_container_url.return_value = "http://localhost:5001"
    app = create_app(docker_mgr)
    return app.test_client()


def test_execute_missing_required_fields_returns_400(client):
    r = client.post("/execute", json={})
    assert r.status_code == 400
    assert "Missing" in r.get_json()["report"]


def test_execute_rejects_traversal_session_id_with_400(client):
    # The new SessionManager validation raises ValueError, which the
    # /execute handler must translate to a 400 (not 500) — otherwise
    # WazzapAgents would treat malicious input as a transient server
    # error and retry indefinitely.
    r = client.post(
        "/execute",
        json={
            "session_id": "../../etc",
            "instruction": "ls",
        },
    )
    assert r.status_code == 400
    body = r.get_json()
    assert body["success"] is False
    assert "outside workdir_base" in body["report"]


def test_execute_rejects_empty_session_id_with_400(client):
    r = client.post(
        "/execute",
        json={
            "session_id": ".",
            "instruction": "ls",
        },
    )
    assert r.status_code == 400
    body = r.get_json()
    assert body["success"] is False
    assert "must not be empty" in body["report"]
