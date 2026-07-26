import hashlib
import os
import sys
from unittest.mock import patch

import pytest

from src.executor_server import (
    MAX_OUTPUT_BYTES,
    MAX_TIMEOUT,
    _clamp_timeout,
    _run_bounded,
    _safe_remove,
    create_executor_app,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    app = create_executor_app()
    return app.test_client(), str(tmp_path)


def test_bash_valid_session_id_runs_inside_workdir_base(client):
    client_, base = client
    command = "cd" if os.name == "nt" else "pwd"
    r = client_.post("/bash", json={"command": command, "session_id": "abc"})
    assert r.status_code == 200, r.data
    out = r.get_json()
    assert out["stdout"].strip().startswith(base + os.sep)
    assert out["returncode"] == 0


def test_bash_rejects_dot_dot_traversal(client):
    client_, _ = client
    r = client_.post("/bash", json={"command": "pwd", "session_id": "../../etc"})
    assert r.status_code == 400
    assert "Invalid session_id" in r.get_json()["error"]


def test_bash_absolute_session_id_is_rejected(client):
    client_, _ = client
    r = client_.post("/bash", json={"command": "pwd", "session_id": "/foo"})
    assert r.status_code == 400


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


def test_execution_output_limit_does_not_limit_workdir_files(tmp_path):
    target = tmp_path / "large-output.bin"
    file_size = MAX_OUTPUT_BYTES + 1
    code = (
        "from pathlib import Path; "
        f"Path({str(target)!r}).write_bytes(b'x' * {file_size})"
    )

    stdout, stderr, returncode, failure = _run_bounded(
        [sys.executable, "-c", code],
        workdir=str(tmp_path),
        timeout=10,
        isolation={},
    )

    assert stdout == ""
    assert stderr == ""
    assert returncode == 0
    assert failure is None
    assert target.stat().st_size == file_size


def test_bash_respects_custom_timeout(client):
    client_, _ = client
    command = f'"{sys.executable}" -c "import time; time.sleep(5)"'
    r = client_.post(
        "/bash",
        json={"command": command, "session_id": "timeout-test", "timeout": 1},
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


def test_duplicate_request_id_executes_command_only_once(client):
    client_, _ = client
    payload = {
        "command": "echo once",
        "session_id": "dedupe-test",
        "request_id": "request-idempotency-0001",
    }
    with patch(
        "src.executor_server._run_bounded", return_value=("once\n", "", 0, None)
    ) as run:
        first = client_.post("/bash", json=payload)
        second = client_.post("/bash", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json()
    assert run.call_count == 1


def test_duplicate_request_survives_executor_app_restart(client):
    client_, _ = client
    payload = {
        "command": "echo durable",
        "session_id": "durable-dedupe",
        "request_id": "request-idempotency-0002",
    }
    with patch(
        "src.executor_server._run_bounded", return_value=("durable\n", "", 0, None)
    ) as run:
        first = client_.post("/bash", json=payload)
        restarted_client = create_executor_app().test_client()
        second = restarted_client.post("/bash", json=payload)

    assert first.get_json() == second.get_json()
    assert run.call_count == 1


def test_corrupt_executor_receipt_fails_closed(client):
    client_, base = client
    request_id = "request-idempotency-corrupt"
    session_dir = os.path.join(base, "corrupt-receipt")
    receipt_dir = os.path.join(session_dir, ".executor_results")
    os.makedirs(receipt_dir, exist_ok=True)
    receipt_name = hashlib.sha256(
        f"bash\0{request_id}".encode("utf-8")
    ).hexdigest() + ".json"
    with open(os.path.join(receipt_dir, receipt_name), "w", encoding="utf-8") as handle:
        handle.write("{not-json")

    with patch("src.executor_server._run_bounded") as run:
        response = client_.post(
            "/bash",
            json={
                "command": "echo must-not-run",
                "session_id": "corrupt-receipt",
                "request_id": request_id,
            },
        )

    assert response.status_code == 503
    assert "refusing" in response.get_json()["error"].lower()
    run.assert_not_called()


def test_rejects_non_object_json(client):
    client_, _ = client
    response = client_.post("/bash", json=["echo", "unsafe"])
    assert response.status_code == 400


def test_executor_auth_rejects_missing_token(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    monkeypatch.setenv("EXECUTOR_API_TOKEN", "executor-secret")
    monkeypatch.setenv("EXECUTOR_REQUIRE_AUTH", "1")
    authenticated_app = create_executor_app()
    authenticated_client = authenticated_app.test_client()

    missing = authenticated_client.post(
        "/bash", json={"command": "echo no", "session_id": "auth-test"}
    )
    assert missing.status_code == 401

    with patch(
        "src.executor_server._run_bounded", return_value=("ok\n", "", 0, None)
    ) as run:
        accepted = authenticated_client.post(
            "/bash",
            json={"command": "echo yes", "session_id": "auth-test"},
            headers={"Authorization": "Bearer executor-secret"},
        )
    assert accepted.status_code == 200
    assert "EXECUTOR_API_TOKEN" not in run.call_args.kwargs["isolation"]["env"]


def test_request_id_rejects_different_command(client):
    client_, _ = client
    request_id = "request-idempotency-conflict"
    with patch(
        "src.executor_server._run_bounded", return_value=("once\n", "", 0, None)
    ) as run:
        first = client_.post(
            "/bash",
            json={"command": "echo one", "session_id": "conflict", "request_id": request_id},
        )
        conflict = client_.post(
            "/bash",
            json={"command": "echo two", "session_id": "conflict", "request_id": request_id},
        )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert run.call_count == 1


def test_executor_auth_defaults_to_required(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    monkeypatch.delenv("EXECUTOR_API_TOKEN", raising=False)
    monkeypatch.delenv("EXECUTOR_REQUIRE_AUTH", raising=False)
    with pytest.raises(RuntimeError, match="EXECUTOR_API_TOKEN"):
        create_executor_app()


def test_unauthenticated_executor_cannot_bind_non_loopback(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    monkeypatch.setenv("EXECUTOR_REQUIRE_AUTH", "0")
    monkeypatch.setenv("EXECUTOR_BIND_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="loopback"):
        create_executor_app()


def test_executor_stops_and_reports_excessive_output(client, monkeypatch):
    import src.executor_server as executor_module

    monkeypatch.setattr(executor_module, "MAX_OUTPUT_BYTES", 1024)
    client_, _ = client
    response = client_.post(
        "/python",
        json={"code": "print('x' * 4096)", "session_id": "bounded-output"},
    )
    assert response.status_code == 200
    assert "output exceeded" in response.get_json()["error"].lower()


def test_executor_exposes_only_allowlisted_skill_environment(client, monkeypatch):
    client_, base = client
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-test-value")
    monkeypatch.setenv("NINEROUTER_URL", "https://router.example.test")
    monkeypatch.setenv("NINEROUTER_KEY", "nine-test-value")
    monkeypatch.setenv("UNLISTED_SECRET", "must-not-leak")
    monkeypatch.setenv("LLM_API_KEY", "service-secret")

    with patch(
        "src.executor_server._run_bounded",
        return_value=("ok\n", "", 0, None),
    ) as run:
        response = client_.post(
            "/bash",
            json={"command": "true", "session_id": "env-boundary"},
        )

    assert response.status_code == 200
    environment = run.call_args.kwargs["isolation"]["env"]
    assert environment["BRAVE_SEARCH_API_KEY"] == "brave-test-value"
    assert environment["NINEROUTER_URL"] == "https://router.example.test"
    assert environment["NINEROUTER_KEY"] == "nine-test-value"
    assert "UNLISTED_SECRET" not in environment
    assert "LLM_API_KEY" not in environment
    assert environment["HOME"] == os.path.join(base, "env-boundary")
    assert environment["TMPDIR"] == os.path.join(base, "env-boundary", ".tmp")


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="Unix UID isolation requires a root test runner",
)
def test_sibling_sessions_run_as_distinct_uids(client, monkeypatch):
    import src.executor_server as executor_module

    monkeypatch.setattr(executor_module, "REQUIRE_UID_ISOLATION", True)
    client_, _ = client
    with patch(
        "src.executor_server._run_bounded",
        return_value=("ok\n", "", 0, None),
    ) as run:
        first = client_.post("/bash", json={"command": "true", "session_id": "uid-a"})
        second = client_.post("/bash", json={"command": "true", "session_id": "uid-b"})

    assert first.status_code == second.status_code == 200
    first_uid = run.call_args_list[0].kwargs["isolation"]["user"]
    second_uid = run.call_args_list[1].kwargs["isolation"]["user"]
    assert first_uid != second_uid
    assert run.call_args_list[0].kwargs["isolation"]["umask"] == 0o077


# --- _clamp_timeout tests ---

def test_clamp_timeout_defaults_on_missing():
    assert _clamp_timeout(None) == 60
    assert _clamp_timeout(0) == 60
    assert _clamp_timeout(-5) == 60


def test_clamp_timeout_defaults_on_invalid_type():
    assert _clamp_timeout("abc") == 60
    assert _clamp_timeout([10]) == 60


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

    call_count = 0

    def failing_remove(path):
        nonlocal call_count
        call_count += 1
        raise OSError("Permission denied")

    monkeypatch.setattr(os, "remove", failing_remove)
    # Should not raise, even though os.remove fails
    _safe_remove(str(f))
    assert call_count == 1
