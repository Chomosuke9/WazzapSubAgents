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


def test_execute_restages_input_files_into_workdir(tmp_path, monkeypatch):
    """Pin the cross-process path-reachability fix.

    Bug: when a caller passes ``input_files`` whose host paths aren't
    bind-mounted into the executor sidecar, the agent's bash/python see
    "file not found" and the user gets back a "tidak ditemukan pada path
    yang dipakai" failure.

    Fix: ``/execute`` re-stages each input into ``<workdir>/.inputs/`` so
    the agent always receives paths inside the bind-mounted workdir.
    Verify the agent ends up being called with paths whose parent is
    ``<workdir>/.inputs`` rather than the caller-supplied source dir.
    """
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    src_dir = tmp_path / "elsewhere"  # NOT inside WORKDIR_BASE
    src_dir.mkdir()
    src_file = src_dir / "user-doc.zip"
    src_file.write_bytes(b"zip-bytes")

    docker_mgr = MagicMock()
    docker_mgr.get_container_url.return_value = "http://localhost:5001"
    app = create_app(docker_mgr)
    test_client = app.test_client()

    captured = {}

    fake_agent = MagicMock()

    def _capture_execute(**kwargs):
        captured.update(kwargs)
        return {
            "session_id": kwargs["session_id"],
            "success": True,
            "report": "ok",
            "output_files": [],
            "processing_time_sec": 0,
        }

    fake_agent.execute.side_effect = _capture_execute

    import threading
    from unittest.mock import patch

    done = threading.Event()
    orig_thread = threading.Thread

    def waiting_thread(*args, **kwargs):
        target = kwargs.get("target") or (args[0] if args else None)

        def wrapped():
            try:
                if target:
                    target()
            finally:
                done.set()

        if "target" in kwargs:
            kwargs["target"] = wrapped
        else:
            args = (wrapped,) + tuple(args[1:])
        return orig_thread(*args, **kwargs)

    with patch("src.app.ExecutorAgent", return_value=fake_agent), patch(
        "src.app.threading.Thread", side_effect=waiting_thread
    ):
        r = test_client.post(
            "/execute",
            json={
                "session_id": "sess-restage",
                "instruction": "extract this archive",
                "input_files": [str(src_file)],
            },
        )
        assert r.status_code == 202
        assert done.wait(timeout=5)

    staged = captured.get("input_files")
    assert staged and len(staged) == 1
    # The agent must have been told the file's reachable path inside the
    # workdir, NOT the caller-supplied path that lives outside any mount.
    assert ".inputs" in staged[0]
    assert staged[0].startswith(str(tmp_path / "work"))
    # Bytes survived the copy.
    with open(staged[0], "rb") as f:
        assert f.read() == b"zip-bytes"
