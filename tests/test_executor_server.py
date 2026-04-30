import os

import pytest

from src.executor_server import create_executor_app, _clamp_timeout, _safe_remove, MAX_TIMEOUT


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
    # The /python endpoint now runs code in a subprocess with cwd set to
    # the session workdir, so ``os.getcwd()`` should return the session dir.
    # Output is captured as stdout/stderr/returncode (same as /bash).
    client_, base = client
    r = client_.post(
        "/python",
        json={"code": "print('ok')", "session_id": "abc"},
    )
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert out["stdout"].strip() == "ok"
    assert out["returncode"] == 0
    assert os.path.isdir(os.path.join(base, "abc"))


def test_bash_respects_custom_timeout(client):
    client_, _ = client
    r = client_.post(
        "/bash",
        json={"command": "sleep 5", "session_id": "timeout-test", "timeout": 1},
    )
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert "timed out (1s)" in out["error"]


def test_python_respects_custom_timeout(client):
    client_, _ = client
    r = client_.post(
        "/python",
        json={"code": "import time; time.sleep(5)", "session_id": "timeout-test", "timeout": 1},
    )
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert "timed out (1s)" in out["error"]


def test_javascript_respects_custom_timeout(client):
    import shutil
    if not shutil.which("node"):
        pytest.skip("node not available in this environment")
    client_, _ = client
    r = client_.post(
        "/javascript",
        json={"code": "setTimeout(() => {}, 5000);", "session_id": "timeout-test", "timeout": 1},
    )
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert "timed out (1s)" in out["error"]


# --- _clamp_timeout tests ---

def test_clamp_timeout_defaults_on_missing():
    assert _clamp_timeout(None) == 10
    assert _clamp_timeout(0) == 10
    assert _clamp_timeout(-5) == 10


def test_clamp_timeout_defaults_on_invalid_type():
    assert _clamp_timeout("abc") == 10
    assert _clamp_timeout([10]) == 10


def test_clamp_timeout_passes_valid_values():
    assert _clamp_timeout(1) == 1
    assert _clamp_timeout(10) == 10
    assert _clamp_timeout(30.5) == 30.5


def test_clamp_timeout_caps_at_max():
    assert _clamp_timeout(MAX_TIMEOUT + 1) == MAX_TIMEOUT
    assert _clamp_timeout(999999) == MAX_TIMEOUT
    assert _clamp_timeout(MAX_TIMEOUT) == MAX_TIMEOUT


# --- _safe_remove tests ---

def test_safe_remove_deletes_existing_file(tmp_path):
    f = tmp_path / "to_delete.txt"
    f.write_text("bye")
    assert f.exists()
    _safe_remove(str(f))
    assert not f.exists()


def test_safe_remove_ignores_missing_file(tmp_path):
    # Should not raise
    _safe_remove(str(tmp_path / "nonexistent.txt"))


def test_safe_remove_ignores_os_error(tmp_path, monkeypatch):
    """Even if os.remove raises, _safe_remove should not propagate the error."""
    f = tmp_path / "stubborn.txt"
    f.write_text("won't go away")

    original_remove = os.remove
    call_count = 0

    def failing_remove(path):
        nonlocal call_count
        call_count += 1
        raise OSError("Permission denied")

    monkeypatch.setattr(os, "remove", failing_remove)
    # Should not raise, even though os.remove fails
    _safe_remove(str(f))
    assert call_count == 1
