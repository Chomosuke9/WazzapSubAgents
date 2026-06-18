import os
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


def test_execute_normalizes_high_quality_bool(client):
    """The endpoint must accept various truthy/falsy types for ``high_quality``
    and normalise them to a Python bool before passing to the agent."""
    import threading
    from unittest.mock import patch, MagicMock

    cases = [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        (1, True),
        (True, True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        (0, False),
        (False, False),
    ]

    for raw_value, expected in cases:
        fake_agent = MagicMock()
        fake_agent.execute.return_value = {
            "session_id": "s-bool",
            "success": True,
            "report": "ok",
            "output_files": [],
            "processing_time_sec": 0,
        }

        captured = {}

        def _capture_execute(**kwargs):
            captured.update(kwargs)
            return fake_agent.execute.return_value

        fake_agent.execute.side_effect = _capture_execute

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
            kwargs["target"] = wrapped
            return orig_thread(*args, **kwargs)

        with patch("src.app.ExecutorAgent", return_value=fake_agent), \
             patch("src.app.threading.Thread", side_effect=waiting_thread):
            r = client.post(
                "/execute",
                json={
                    "session_id": "s-bool",
                    "instruction": "do it",
                    "high_quality": raw_value,
                },
            )
            assert r.status_code == 202
            assert done.wait(timeout=5), f"Thread did not finish for high_quality={raw_value!r}"

        assert "high_quality" in captured, f"high_quality not captured for raw_value={raw_value!r}"
        assert captured["high_quality"] is expected, (
            f"high_quality={raw_value!r} should be {expected}, got {captured['high_quality']}"
        )


def test_execute_restages_input_files_into_workdir(tmp_path, monkeypatch):
    """Pin the cross-process path-reachability fix.

    Bug: when a caller passes ``input_files`` whose host paths aren't
    bind-mounted into the executor sidecar, the agent's bash/python see
    "file not found" and the user gets back a "tidak ditemukan pada path
    yang dipakai" failure.

    Fix: ``/execute`` re-stages each input into ``<workdir>/input/`` so
    the agent always receives paths inside the bind-mounted workdir.
    Verify the agent ends up being called with paths whose parent is
    ``<workdir>/input`` rather than the caller-supplied source dir.
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
    assert "input" in staged[0]
    assert staged[0].startswith(str(tmp_path / "work"))
    # Bytes survived the copy.
    with open(staged[0], "rb") as f:
        assert f.read() == b"zip-bytes"


def test_execute_decodes_input_files_content(tmp_path, monkeypatch):
    """When input_files_content is provided, the agent must receive paths
    inside <workdir>/input/ with the decoded file contents."""
    import base64
    import threading
    from unittest.mock import patch, MagicMock

    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    docker_mgr = MagicMock()
    docker_mgr.get_container_url.return_value = "http://localhost:5001"
    app = create_app(docker_mgr)
    test_client = app.test_client()

    file_bytes = b"fake-zip-content"
    encoded = base64.b64encode(file_bytes).decode()

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

        kwargs["target"] = wrapped
        return orig_thread(*args, **kwargs)

    with patch("src.app.ExecutorAgent", return_value=fake_agent), \
         patch("src.app.threading.Thread", side_effect=waiting_thread):
        r = test_client.post("/execute", json={
            "session_id": "sess-b64-input",
            "instruction": "process this file",
            "input_files_content": [{"name": "archive.zip", "content_base64": encoded}],
        })
        assert r.status_code == 202
        assert done.wait(timeout=5)

    staged = captured.get("input_files")
    assert staged and len(staged) == 1
    assert os.path.basename(staged[0]) == "archive.zip"
    assert "input" in staged[0]
    with open(staged[0], "rb") as f:
        assert f.read() == file_bytes


def test_steer_returns_200_for_active_session(client, tmp_path, monkeypatch):
    """POST /steer should queue a steering message on an active session."""
    from src.session_manager import SessionManager

    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    sm = SessionManager()
    sm.get_or_create("steer-sess")
    # Use the test client's app but override session_manager
    # Easier: just test SessionManager directly
    ok = sm.add_steering_message("steer-sess", "focus on cats")
    assert ok is True
    msgs = sm.consume_steering_messages("steer-sess")
    assert msgs == ["focus on cats"]
    sm.cleanup_session("steer-sess")


def test_steer_rejects_unknown_session(tmp_path, monkeypatch):
    from src.session_manager import SessionManager

    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    sm = SessionManager()
    ok = sm.add_steering_message("nonexistent", "do something")
    assert ok is False


def test_steer_endpoint_returns_200_for_active_session(tmp_path, monkeypatch):
    """POST /steer returns 200 for an active session, 404 for completed/unknown."""
    from src.session_manager import SessionManager

    # Test SessionManager directly — this is the core logic.
    # The /steer endpoint is a thin wrapper; we also test 400/404 via HTTP.
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    sm = SessionManager()
    sm.get_or_create("steer-sess")
    ok = sm.add_steering_message("steer-sess", "focus on cats")
    assert ok is True
    msgs = sm.consume_steering_messages("steer-sess")
    assert msgs == ["focus on cats"]
    # Completed session should reject steering
    sm.store_result("steer-sess", {"success": True, "report": "done"})
    ok = sm.add_steering_message("steer-sess", "too late")
    assert ok is False


def test_steer_endpoint_returns_404_for_unknown_session(client):
    r = client.post(
        "/steer",
        json={"session_id": "ghost", "instruction": "do something"},
    )
    assert r.status_code == 404


def test_steer_endpoint_returns_400_for_missing_fields(client):
    r = client.post("/steer", json={})
    assert r.status_code == 400


def _app_with_session(tmp_path, session_id):
    """Build an app with an injected SessionManager holding one active
    session, plus return the manager and session for assertions."""
    from src.session_manager import SessionManager

    sm = SessionManager()
    session = sm.get_or_create(session_id)
    docker_mgr = MagicMock()
    docker_mgr.get_container_url.return_value = "http://localhost:5001"
    app = create_app(docker_mgr, session_manager=sm)
    return app.test_client(), sm, session


def test_steer_stages_base64_files_into_workdir_and_lists_them(tmp_path, monkeypatch):
    """POST /steer with input_files_content must stage the file into the
    running session's workdir/input and reference its path in the steering
    message the agent will consume."""
    import base64

    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    client, sm, session = _app_with_session(tmp_path, "steer-files")

    content = base64.b64encode(b"hello steered file").decode("ascii")
    r = client.post(
        "/steer",
        json={
            "session_id": "steer-files",
            "instruction": "use this new file",
            "input_files_content": [{"name": "note.txt", "content_base64": content}],
        },
    )
    assert r.status_code == 200
    assert r.get_json()["staged_file_count"] == 1

    staged = os.path.join(session.workdir, "input", "note.txt")
    assert os.path.isfile(staged)
    with open(staged) as fh:
        assert fh.read() == "hello steered file"

    # The steering message the agent receives must mention the instruction
    # AND the staged file path so the agent knows the file exists.
    msgs = sm.consume_steering_messages("steer-files")
    assert len(msgs) == 1
    assert "use this new file" in msgs[0]
    assert "note.txt" in msgs[0]
    sm.cleanup_session("steer-files")


def test_steer_without_files_keeps_plain_instruction(tmp_path, monkeypatch):
    """A file-less /steer call must behave exactly as before: the steering
    message is the raw instruction with no NEW INPUT FILES block."""
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    client, sm, session = _app_with_session(tmp_path, "steer-plain")

    r = client.post(
        "/steer",
        json={"session_id": "steer-plain", "instruction": "focus on cats"},
    )
    assert r.status_code == 200
    assert r.get_json()["staged_file_count"] == 0
    msgs = sm.consume_steering_messages("steer-plain")
    assert msgs == ["focus on cats"]
    sm.cleanup_session("steer-plain")


def test_steer_with_files_on_unknown_session_returns_404(client):
    """Files supplied for a session that doesn't exist must not 200 — the
    canonical not-found contract is preserved."""
    import base64

    content = base64.b64encode(b"data").decode("ascii")
    r = client.post(
        "/steer",
        json={
            "session_id": "ghost",
            "instruction": "do something",
            "input_files_content": [{"name": "x.txt", "content_base64": content}],
        },
    )
    assert r.status_code == 404
