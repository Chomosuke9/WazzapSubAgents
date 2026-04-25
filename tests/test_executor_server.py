import os

import pytest

from src.executor_server import create_executor_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    app = create_executor_app()
    return app.test_client(), str(tmp_path)


def test_bash_valid_session_id_runs_inside_workdir_base(client):
    client_, base = client
    r = client_.post("/bash", json={"command": "pwd", "session_id": "abc"})
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert out["stdout"].strip().startswith(base + os.sep)
    assert out["returncode"] == 0


def test_bash_rejects_dot_dot_traversal(client):
    client_, _ = client
    r = client_.post("/bash", json={"command": "pwd", "session_id": "../../etc"})
    assert r.status_code == 400
    assert "outside workdir_base" in r.get_json()["error"]


def test_bash_absolute_session_id_is_contained(client):
    # ``/foo`` must be sanitized the same way SessionManager sanitizes it,
    # otherwise the executor would write to the host root while the main
    # service collects from <workdir_base>/foo.
    client_, base = client
    r = client_.post("/bash", json={"command": "pwd", "session_id": "/foo"})
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert out["stdout"].strip().startswith(base + os.sep)


def test_bash_rejects_empty_session_id(client):
    client_, _ = client
    r = client_.post("/bash", json={"command": "pwd", "session_id": "."})
    assert r.status_code == 400


def test_python_rejects_dot_dot_traversal(client):
    client_, _ = client
    r = client_.post(
        "/python",
        json={"code": "print(1)", "session_id": "../../etc"},
    )
    assert r.status_code == 400


def test_python_valid_session_id(client):
    # The /python endpoint runs ``exec`` in the server process so cwd is
    # not inherently the session workdir, but the workdir must still be
    # created on disk so the agent can write files there explicitly.
    client_, base = client
    r = client_.post(
        "/python",
        json={"code": "print('ok')", "session_id": "abc"},
    )
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert out["output"].strip() == "ok"
    assert os.path.isdir(os.path.join(base, "abc"))
