import base64
import hashlib
import os
from unittest.mock import MagicMock, patch

import pytest

from src.app import create_app
from src.input_staging import stage_request_inputs
from src.session_manager import SessionManager, SessionPersistenceError
from src.upload_store import UploadStore


@pytest.fixture
def protocol(tmp_path, monkeypatch):
    work = tmp_path / "work"
    state = tmp_path / "state"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("WORKDIR_BASE", str(work))
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(state))
    monkeypatch.setenv("SUBAGENT_INPUT_SOURCE_ROOT", str(uploads))
    manager = SessionManager(idle_timeout=600)
    docker = MagicMock()
    app = create_app(docker_mgr=docker, session_manager=manager, container_url="http://executor:5001")
    return app.test_client(), manager, uploads


def test_execute_fails_closed_when_a_requested_file_is_missing(protocol):
    client, manager, uploads = protocol
    response = client.post(
        "/execute",
        json={
            "session_id": "missing-file",
            "instruction": "read it",
            "input_files": [str(uploads / "does-not-exist.pdf")],
        },
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["accepted"] is False
    assert body["requested_file_count"] == 1
    assert body["staged_file_count"] == 0
    assert body["file_errors"][0]["code"] == "source_unavailable"
    assert manager.get_session("missing-file") is None


def test_execute_returns_verified_manifest_and_is_idempotent(protocol):
    client, manager, _uploads = protocol
    content = b"verified document bytes"
    encoded = base64.b64encode(content).decode("ascii")
    started = []

    class DeferredThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            started.append(self.target)

    payload = {
        "session_id": "execute-idempotent",
        "instruction": "inspect document",
        "input_files_content": [
            {
                "name": "document.bin",
                "content_base64": encoded,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    with patch("src.app.threading.Thread", DeferredThread):
        first = client.post("/execute", json=payload)
        replay = client.post("/execute", json=payload)
        conflict = client.post("/execute", json={**payload, "instruction": "different task"})

    assert first.status_code == 202
    manifest = first.get_json()
    assert manifest["accepted"] is True
    assert manifest["requested_file_count"] == manifest["staged_file_count"] == 1
    assert manifest["staged_files"][0]["size"] == len(content)
    assert manifest["staged_files"][0]["sha256"] == hashlib.sha256(content).hexdigest()
    assert replay.status_code == 202
    assert replay.get_json()["idempotent_replay"] is True
    assert replay.get_json()["staged_files"] == manifest["staged_files"]
    assert conflict.status_code == 409
    assert len(started) == 1
    manager.cleanup_session("execute-idempotent")


def test_strict_base64_and_integrity_mismatch_are_rejected(protocol):
    client, _manager, _uploads = protocol
    bad_base64 = client.post(
        "/execute",
        json={
            "session_id": "bad-base64",
            "instruction": "read",
            "input_files_content": [{"name": "x.bin", "content_base64": "not base64!"}],
        },
    )
    bad_hash = client.post(
        "/execute",
        json={
            "session_id": "bad-hash",
            "instruction": "read",
            "input_files_content": [{
                "name": "x.bin",
                "content_base64": base64.b64encode(b"abc").decode("ascii"),
                "sha256": "0" * 64,
            }],
        },
    )
    assert bad_base64.status_code == 422
    assert bad_hash.status_code == 422
    assert bad_hash.get_json()["staged_file_count"] == 0


def test_steering_ack_transitions_from_queued_to_consumed_and_replays(protocol):
    client, manager, _uploads = protocol
    session = manager.get_or_create("steering-session")
    content = base64.b64encode(b"new file").decode("ascii")
    payload = {
        "session_id": "steering-session",
        "steering_id": "steer-stable-1",
        "instruction": "use the new file",
        "input_files_content": [{"name": "new.txt", "content_base64": content}],
    }

    first = client.post("/steer", json=payload)
    replay = client.post("/steer", json=payload)
    assert first.status_code == replay.status_code == 202
    assert first.get_json()["state"] == "queued"
    assert replay.get_json()["idempotent_replay"] is True
    assert replay.get_json()["staged_files"] == first.get_json()["staged_files"]
    assert len(list((os.path.join(session.workdir, "input") for _ in [0]))) == 1
    assert len(os.listdir(os.path.join(session.workdir, "input"))) == 1

    queued = client.get("/sessions/steering-session/steering/steer-stable-1")
    assert queued.status_code == 200
    assert queued.get_json()["state"] == "queued"
    messages = manager.consume_steering_messages("steering-session")
    assert len(messages) == 1 and "new.txt" in messages[0]
    consumed = client.get("/sessions/steering-session/steering/steer-stable-1")
    assert consumed.get_json()["state"] == "consumed"
    assert consumed.get_json()["consumed_at"] is not None
    manager.cleanup_session("steering-session")


def test_previous_session_files_are_rehydrated_or_request_fails(protocol):
    client, manager, uploads = protocol
    original = uploads / "prior.txt"
    original.write_bytes(b"prior bytes")
    previous = manager.get_or_create("previous-session")
    staged = stage_request_inputs(
        previous.workdir,
        [str(original)],
        [],
        source_root=str(uploads),
        forbidden_source_root=str(manager._workdir_base),
    )
    assert staged.complete
    manager.set_request_manifest("previous-session", staged.as_dict())
    manager.store_messages("previous-session", [])
    manager.store_result("previous-session", {"success": True, "report": "done", "output_files": []})

    class DeferredThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            pass

    with patch("src.app.threading.Thread", DeferredThread):
        response = client.post(
            "/execute",
            json={
                "session_id": "continued-session",
                "previous_session_id": "previous-session",
                "instruction": "continue",
            },
        )
    assert response.status_code == 202
    rehydrated = response.get_json()["rehydrated_files"]
    assert len(rehydrated) == 1
    assert rehydrated[0]["sha256"] == hashlib.sha256(b"prior bytes").hexdigest()
    assert open(rehydrated[0]["path"], "rb").read() == b"prior bytes"
    manager.cleanup_session("continued-session")
    manager.cleanup_session("previous-session")


def test_caller_cannot_stage_a_sibling_session_file(protocol):
    _client, manager, _uploads = protocol
    victim = manager.get_or_create("victim-session")
    secret = os.path.join(victim.workdir, "secret.txt")
    with open(secret, "wb") as handle:
        handle.write(b"secret")
    attacker = manager.get_or_create("attacker-session")
    result = stage_request_inputs(
        attacker.workdir,
        [secret],
        [],
        source_root=os.path.dirname(manager._workdir_base),
        forbidden_source_root=manager._workdir_base,
    )
    assert not result.complete
    assert result.staged_file_count == 0
    assert "cross-session" in result.file_errors[0].error
    manager.cleanup_session("attacker-session")
    manager.cleanup_session("victim-session")


def test_completion_closes_steering_admission_atomically(protocol):
    _client, manager, _uploads = protocol
    manager.get_or_create("completion-race")
    assert manager.try_begin_completion("completion-race") is True
    envelope, state = manager.queue_steering(
        "completion-race",
        "too-late-steer",
        "too late",
        "f" * 64,
        {},
    )
    assert envelope is None
    assert state == "inactive"
    manager.cleanup_session("completion-race")


def test_completion_callback_flag_changes_only_after_delivery(protocol, monkeypatch):
    _client, manager, _uploads = protocol
    import src.session_manager as session_module

    manager.get_or_create("durable-callback")
    manager.set_callback("durable-callback", "http://callback.invalid/complete", None)
    monkeypatch.setattr(session_module, "_WEBHOOK_RETRY_MAX", 1)

    class SyncThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            if self.target:
                self.target()

    with patch("src.session_manager.threading.Thread", SyncThread), patch(
        "src.session_manager.requests.post", side_effect=OSError("network down")
    ):
        manager.store_result(
            "durable-callback",
            {"success": True, "report": "done", "output_files": []},
        )

    session = manager.get_session("durable-callback")
    assert session is not None
    assert session._callback_sent is False
    assert session._callback_pending is True
    outbox = list((manager._outbox_dir and os.path.join(manager._outbox_dir, name)) for name in os.listdir(manager._outbox_dir))
    assert len(outbox) == 1 and os.path.isfile(outbox[0])
    manager.cleanup_session("durable-callback")


def test_large_output_has_authenticated_verified_download(protocol, monkeypatch):
    client, manager, _uploads = protocol
    import src.app as app_module
    import src.session_manager as session_module

    monkeypatch.setattr(app_module, "_API_TOKEN", "transfer-secret")
    monkeypatch.setattr(session_module, "_MAX_INLINE_FILE_BYTES", 1)
    session = manager.get_or_create("large-output")
    output = os.path.join(session.workdir, "result.bin")
    with open(output, "wb") as handle:
        handle.write(b"large result bytes")
    manager.store_result(
        "large-output",
        {"success": True, "report": "done", "output_files": [output]},
    )

    delivery = manager.get_result("large-output", delivery=True)
    assert delivery is not None
    assert delivery["output_files_content"] == []
    omitted = delivery["output_files_omitted"]
    assert len(omitted) == 1
    descriptor = omitted[0]
    assert descriptor["size_bytes"] == len(b"large result bytes")
    assert descriptor["sha256"] == hashlib.sha256(b"large result bytes").hexdigest()
    assert descriptor["download_url"].startswith("/sessions/large-output/outputs/")

    assert client.get(descriptor["download_url"]).status_code == 401
    downloaded = client.get(
        descriptor["download_url"],
        headers={"Authorization": "Bearer transfer-secret"},
    )
    assert downloaded.status_code == 200
    assert downloaded.data == b"large result bytes"
    assert downloaded.headers["X-Content-SHA256"] == descriptor["sha256"]
    manager.cleanup_session("large-output")


def test_chunked_upload_is_idempotent_verified_and_claimed(protocol, monkeypatch):
    client, manager, _uploads = protocol
    import src.app as app_module

    monkeypatch.setattr(app_module, "_API_TOKEN", "api-secret")
    headers = {"Authorization": "Bearer api-secret"}
    data = b"0123456789abcdef"
    upload_id = "a" * 32
    identity = {
        "upload_id": upload_id,
        "filename": "large.bin",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    initiated = client.post("/uploads/init", json=identity, headers=headers)
    replay_init = client.post("/uploads/init", json=identity, headers=headers)
    assert initiated.status_code == 201
    assert replay_init.status_code == 200
    assert replay_init.get_json()["idempotent_replay"] is True

    first = data[:8]
    second = data[8:]
    chunk0 = client.put(
        f"/uploads/{upload_id}/chunks/0",
        data=first,
        headers={**headers, "Content-Range": f"bytes 0-7/{len(data)}"},
    )
    replay_chunk0 = client.put(
        f"/uploads/{upload_id}/chunks/0",
        data=first,
        headers={**headers, "Content-Range": f"bytes 0-7/{len(data)}"},
    )
    chunk1 = client.put(
        f"/uploads/{upload_id}/chunks/1",
        data=second,
        headers={**headers, "Content-Range": f"bytes 8-15/{len(data)}"},
    )
    assert chunk0.status_code == chunk1.status_code == 201
    assert replay_chunk0.status_code == 200
    completed = client.post(f"/uploads/{upload_id}/complete", headers=headers)
    assert completed.status_code == 200
    assert completed.get_json()["complete"] is True

    class DeferredThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            pass

    with patch("src.app.threading.Thread", DeferredThread):
        executed = client.post(
            "/execute",
            json={
                "session_id": "uploaded-input",
                "instruction": "read uploaded file",
                "input_files": [{
                    "upload_id": upload_id,
                    "name": "large.bin",
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }],
            },
            headers=headers,
        )
    assert executed.status_code == 202
    manifest = executed.get_json()
    assert manifest["requested_file_count"] == manifest["staged_file_count"] == 1
    assert manifest["staged_files"][0]["source"] == "upload"
    assert manifest["staged_files"][0]["sha256"] == hashlib.sha256(data).hexdigest()
    with open(manifest["staged_files"][0]["path"], "rb") as handle:
        assert handle.read() == data
    # Once the durable session manifest owns the verified copy, the temporary
    # upload is deleted so completed jobs cannot exhaust active-upload quota.
    assert client.post(f"/uploads/{upload_id}/complete", headers=headers).status_code == 404
    manager.cleanup_session("uploaded-input")


def test_api_token_rejects_missing_or_wrong_bearer(protocol, monkeypatch):
    client, _manager, _uploads = protocol
    import src.app as app_module

    monkeypatch.setattr(app_module, "_API_TOKEN", "api-secret")
    payload = {"session_id": "auth-check", "instruction": "do work"}
    assert client.post("/execute", json=payload).status_code == 401
    assert client.post(
        "/execute",
        json=payload,
        headers={"Authorization": "Bearer wrong"},
    ).status_code == 401


def test_restart_turns_abandoned_active_session_into_terminal_result(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(tmp_path / "state"))
    manager = SessionManager(idle_timeout=600)
    manager.begin_execution("interrupted", "fingerprint")
    manager.mark_execution_started("interrupted")

    restarted = SessionManager(idle_timeout=600)
    session = restarted.get_session("interrupted")
    assert session is not None
    assert session.status == "completed"
    assert session.result["error_code"] == "interrupted_by_restart"


def test_new_session_fails_closed_when_state_cannot_be_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(tmp_path / "state"))
    manager = SessionManager(idle_timeout=600)
    monkeypatch.setattr(manager, "_atomic_json", MagicMock(side_effect=OSError("disk full")))

    with pytest.raises(SessionPersistenceError, match="Could not persist"):
        manager.get_or_create("not-accepted")
    assert manager.get_session("not-accepted") is None


def test_corrupt_session_state_blocks_session_id_reuse(tmp_path, monkeypatch):
    work = tmp_path / "work"
    state = tmp_path / "state"
    state.mkdir()
    (state / "corrupt-session.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("WORKDIR_BASE", str(work))
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(state))

    manager = SessionManager(idle_timeout=600)
    with pytest.raises(SessionPersistenceError, match="unreadable durable state"):
        manager.begin_execution("corrupt-session", "fingerprint")


def test_completion_sequence_remains_stable_after_late_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(tmp_path / "state"))
    manager = SessionManager(idle_timeout=600)
    manager.get_or_create("stable-completion")
    manager.set_callback(
        "stable-completion",
        "http://callback.invalid/complete",
        "http://callback.invalid/progress",
    )

    with patch.object(manager, "_fire_webhook"):
        manager.store_result(
            "stable-completion",
            {"success": True, "report": "done", "output_files": []},
        )
        session = manager.get_session("stable-completion")
        assert session is not None
        completion_sequence = session.callback_sequence
        manager.append_progress("stable-completion", {"step": "late"})

    assert completion_sequence > 0
    assert session.event_sequence > completion_sequence
    assert session.callback_sequence == completion_sequence

    restarted = SessionManager(idle_timeout=600)
    recovered = restarted.get_session("stable-completion")
    assert recovered is not None
    assert recovered.callback_sequence == completion_sequence
    assert recovered.next_delivery_sequence == completion_sequence


def test_cleanup_does_not_release_session_id_when_state_removal_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(tmp_path / "state"))
    manager = SessionManager(idle_timeout=600)
    manager.get_or_create("cleanup-failure")
    state_path = manager._state_path("cleanup-failure")
    original_unlink = os.unlink

    def fail_state_unlink(path):
        if os.path.realpath(path) == os.path.realpath(state_path):
            raise OSError("state is locked")
        return original_unlink(path)

    monkeypatch.setattr("src.session_manager.os.unlink", fail_state_unlink)
    manager.cleanup_session("cleanup-failure")

    assert manager.get_session("cleanup-failure") is not None
    assert os.path.isfile(state_path)


def test_upload_keeps_chunks_if_complete_metadata_write_fails(tmp_path, monkeypatch):
    store = UploadStore(str(tmp_path / "uploads"))
    content = b"durable upload"
    upload_id = "b" * 32
    store.initiate(
        upload_id=upload_id,
        filename="input.bin",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    store.put_chunk(upload_id, 0, f"bytes 0-{len(content) - 1}/{len(content)}", content)
    monkeypatch.setattr(store, "_atomic_json", MagicMock(side_effect=OSError("disk full")))

    with pytest.raises(OSError, match="disk full"):
        store.complete(upload_id)
    assert os.path.isdir(os.path.join(store._directory(upload_id), "chunks"))
