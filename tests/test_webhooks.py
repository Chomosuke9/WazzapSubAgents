"""
Quick integration test for webhook push notification feature.
No external HTTP server needed -- we monkeypatch _fire_webhook to collect payloads.
"""
import time
import os
from unittest.mock import MagicMock, patch

import requests as req_module

import src.session_manager as sm_module

from src.session_manager import SessionManager


class SyncThread:
    """Run webhook delivery inline so assertions see the terminal state."""

    def __init__(self, target=None, daemon=None, **_kwargs):
        self._target = target

    def start(self):
        if self._target:
            self._target()


def test_webhook_flow():
    sm = SessionManager(idle_timeout=60)
    sm.get_or_create("test-session-1")

    captured = []

    def fake_fire(url, payload):
        captured.append((url, payload))

    sm._fire_webhook = fake_fire

    sm.set_callback("test-session-1", "http://callback.url/complete", "http://callback.url/progress")

    # Simulate progress
    sm.append_progress("test-session-1", {"step": "bash:ls", "detail": "ls -la", "timestamp": time.time()})

    # Simulate result storage -> should fire callback
    sm.store_result("test-session-1", {"success": True, "report": "done"})

    progress_calls = [p for url, p in captured if p.get("type") == "progress"]
    complete_calls = [p for url, p in captured if p.get("type") == "complete"]

    assert len(progress_calls) >= 1, f"Expected at least 1 progress webhook, got {len(progress_calls)}"
    assert len(complete_calls) == 1, f"Expected exactly 1 complete webhook, got {len(complete_calls)}"
    assert complete_calls[0]["result"]["success"] is True
    assert progress_calls[0]["entry"]["step"] == "bash:ls"

    print("Webhook flow test passed!")


def test_no_double_fire():
    sm = SessionManager(idle_timeout=60)
    sm.get_or_create("test-session-2")

    captured = []

    def fake_fire(url, payload):
        captured.append((url, payload))

    sm._fire_webhook = fake_fire

    sm.set_callback("test-session-2", "http://callback.url/complete", None)
    sm.store_result("test-session-2", {"success": True, "report": "done"})
    sm.store_result("test-session-2", {"success": True, "report": "done again"})

    complete_calls = [p for url, p in captured if p.get("type") == "complete"]
    assert len(complete_calls) == 1, f"Expected exactly 1 complete webhook (no double fire), got {len(complete_calls)}"

    print("No double fire test passed!")


def test_no_crash_on_bad_webhook():
    sm = SessionManager(idle_timeout=60)
    sm.get_or_create("test-session-3")
    sm.set_callback("test-session-3", "http://localhost:99999/nope", None)

    # Should not raise; real _fire_webhook uses try/except + thread
    sm.store_result("test-session-3", {"success": True, "report": "done"})
    time.sleep(0.3)
    print("No crash on bad webhook: OK")


def test_terminal_callback_rejection_moves_to_dead_letter_and_survives_restart(
    tmp_path, monkeypatch,
):
    state = tmp_path / "state"
    work = tmp_path / "work"
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(state))
    monkeypatch.setenv("WORKDIR_BASE", str(work))
    monkeypatch.setattr(sm_module, "_WEBHOOK_RETRY_MAX", 5)
    response = MagicMock()
    response.status_code = 422
    response.json.return_value = {
        "status": "invalid_output",
        "retryable": False,
    }
    response.raise_for_status.side_effect = req_module.exceptions.HTTPError("422")

    manager = SessionManager(idle_timeout=60)
    with patch("src.session_manager.threading.Thread", SyncThread), patch(
        "src.session_manager.requests.post", return_value=response,
    ) as post:
        manager.get_or_create("terminal-rejection")
        manager.set_callback(
            "terminal-rejection",
            "http://callback.invalid/complete",
            None,
            {"chat_id": "chat@g.us"},
        )
        manager.store_result(
            "terminal-rejection",
            {"success": True, "report": "done", "output_files": []},
        )

    assert post.call_count == 1
    entry = manager.list_callback_outbox()[0]
    assert entry["state"] == "dead_letter"
    assert entry["callback_status"] == 422
    assert "invalid_output" in entry["callback_error"]
    assert os.listdir(manager._outbox_dir) == []
    assert len(os.listdir(manager._dead_letter_dir)) == 1

    restarted = SessionManager(idle_timeout=60)
    recovered = restarted.get_session("terminal-rejection")
    assert recovered is not None
    assert recovered.callback_context == {"chat_id": "chat@g.us"}
    assert recovered._callback_dead_letter is True
    assert recovered._callback_pending is False
    assert restarted.list_callback_outbox()[0]["state"] == "dead_letter"


def test_manual_retry_delivers_dead_letter_and_clears_outbox(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    manager = SessionManager(idle_timeout=60)
    terminal = MagicMock(status_code=422)
    terminal.json.return_value = {"status": "invalid_output", "retryable": False}
    success = MagicMock(status_code=200)
    success.json.return_value = {"status": "ok"}
    success.raise_for_status.return_value = None

    with patch("src.session_manager.threading.Thread", SyncThread), patch(
        "src.session_manager.requests.post", return_value=terminal,
    ):
        manager.get_or_create("retry-dead-letter")
        manager.set_callback("retry-dead-letter", "http://callback/complete", None)
        manager.store_result(
            "retry-dead-letter",
            {"success": True, "report": "done", "output_files": []},
        )
    assert manager.list_callback_outbox()[0]["state"] == "dead_letter"

    with patch("src.session_manager.threading.Thread", SyncThread), patch(
        "src.session_manager.requests.post", return_value=success,
    ) as post:
        manager.retry_callback("retry-dead-letter")

    assert post.call_count == 1
    session = manager.get_session("retry-dead-letter")
    assert session is not None and session._callback_sent is True
    assert manager.list_callback_outbox() == []
    assert not os.path.exists(manager._outbox_path(manager._completion_payload(session)))
    assert not os.path.exists(manager._dead_letter_path(manager._completion_payload(session)))


def test_discard_stops_pending_callback_without_deleting_result(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBAGENT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path / "work"))
    monkeypatch.setattr(sm_module, "_WEBHOOK_RETRY_MAX", 1)
    manager = SessionManager(idle_timeout=60)

    with patch("src.session_manager.threading.Thread", SyncThread), patch(
        "src.session_manager.requests.post", side_effect=OSError("offline"),
    ):
        manager.get_or_create("discard-pending")
        manager.set_callback("discard-pending", "http://callback/complete", None)
        manager.store_result(
            "discard-pending",
            {"success": True, "report": "retained", "output_files": []},
        )

    assert manager.list_callback_outbox()[0]["state"] == "pending"
    discarded = manager.discard_callback("discard-pending")
    session = manager.get_session("discard-pending")
    assert discarded["state"] == "discarded"
    assert session is not None and session.result["report"] == "retained"
    assert session.callback_result["report"] == "retained"
    assert manager.list_callback_outbox() == []
    assert os.listdir(manager._outbox_dir) == []


def test_polling_unchanged():
    sm = SessionManager(idle_timeout=60)
    sm.get_or_create("test-session-4")
    sm.store_result("test-session-4", {"success": True, "report": "done"})
    result = sm.get_result("test-session-4")
    assert result is not None
    assert result["success"] is True
    print("Polling unchanged: OK")


def test_progress_logs_stored():
    sm = SessionManager(idle_timeout=60)
    session = sm.get_or_create("test-session-5")
    sm.append_progress("test-session-5", {"step": "python:exec", "detail": "print(1)", "timestamp": time.time()})
    assert len(session.progress_logs) == 1
    assert session.progress_logs[0]["step"] == "python:exec"
    print("Progress logs stored: OK")


if __name__ == "__main__":
    test_webhook_flow()
    test_no_double_fire()
    test_no_crash_on_bad_webhook()
    test_polling_unchanged()
    test_progress_logs_stored()
    print("\nAll tests passed!")


def test_413_strips_output_files_content_and_retries():
    """On 413, _fire_webhook strips output_files_content and retries with smaller payload."""
    sm = SessionManager()

    # Build a response mock for 413
    resp_413 = MagicMock()
    resp_413.status_code = 413
    resp_413.raise_for_status.side_effect = req_module.exceptions.HTTPError("413")

    # Build a response mock for 200
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.raise_for_status.return_value = None

    call_payloads = []

    def fake_post(url, json=None, timeout=None):
        call_payloads.append(json)
        if len(call_payloads) == 1:
            return resp_413
        return resp_200

    class SyncThread:
        """Runs target synchronously so patches stay active."""
        def __init__(self, target=None, daemon=None, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    with patch("src.session_manager.requests.post", side_effect=fake_post), \
         patch("src.session_manager.threading.Thread", SyncThread):
        sm.get_or_create("sess-413-test")
        sm.set_callback("sess-413-test", "http://localhost:9999/cb", None)
        sm.store_result("sess-413-test", {
            "success": True,
            "report": "video downloaded",
            "output_files": [],
            "output_files_content": [{"name": "video.mp4", "content_base64": "AAAA", "mime": "video/mp4"}],
        })

    sm.cleanup_session("sess-413-test")

    assert len(call_payloads) >= 2, f"Expected at least 2 requests, got {len(call_payloads)}"

    # First request should have output_files_content (original payload)
    first_result = call_payloads[0].get("result") or {}
    assert "output_files_content" in first_result, "First request should have output_files_content"

    # Second request should NOT have output_files_content (stripped)
    second_result = call_payloads[1].get("result") or {}
    assert "output_files_content" not in second_result, (
        f"Second request after 413 must NOT contain output_files_content, got keys: {list(second_result.keys())}"
    )
    assert second_result.get("output_files_content_dropped") is True, (
        "Stripped payload must include output_files_content_dropped=True"
    )


def test_413_fallback_resets_attempt_counter():
    """After 413 fallback, attempt counter resets so stripped payload gets full retries."""
    sm = SessionManager()

    resp_413 = MagicMock()
    resp_413.status_code = 413
    resp_413.raise_for_status.side_effect = req_module.exceptions.HTTPError("413")

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.raise_for_status.return_value = None

    call_count = [0]

    def fake_post(url, json=None, timeout=None):
        call_count[0] += 1
        n = call_count[0]
        if n == 1:
            return resp_413        # 413 -> strip and reset
        elif n in (2, 3, 4):
            # Simulate connection errors on attempts 1-3 after reset
            raise req_module.exceptions.ConnectionError("connection refused")
        else:
            return resp_200        # Eventually succeeds

    class SyncThread:
        """Runs target synchronously so patches stay active."""
        def __init__(self, target=None, daemon=None, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    # Lower WEBHOOK_RETRY_MAX before store_result so _fire_webhook captures 5
    original_max = sm_module._WEBHOOK_RETRY_MAX
    sm_module._WEBHOOK_RETRY_MAX = 5

    try:
        with patch("src.session_manager.requests.post", side_effect=fake_post), \
             patch("src.session_manager.time.sleep"), \
             patch("src.session_manager.threading.Thread", SyncThread):
            sm.get_or_create("sess-413-reset")
            sm.set_callback("sess-413-reset", "http://localhost:9999/cb", None)
            sm.store_result("sess-413-reset", {
                "success": True,
                "report": "done",
                "output_files_content": [{"name": "f.mp4", "content_base64": "AAA", "mime": "video/mp4"}],
            })
    finally:
        sm_module._WEBHOOK_RETRY_MAX = original_max

    sm.cleanup_session("sess-413-reset")

    # Should have eventually succeeded: 1 (413) + 3 (errors) + 1 (200) = 5 total calls
    assert call_count[0] == 5, (
        f"Expected 5 total requests (1x413 + 3xError + 1x200), got {call_count[0]}"
    )


def test_413_no_double_strip():
    """Second 413 after strip does NOT re-strip; guard prevents infinite reset loop."""
    sm = SessionManager()

    resp_413 = MagicMock()
    resp_413.status_code = 413
    resp_413.raise_for_status.side_effect = req_module.exceptions.HTTPError("413 Too Large")

    call_count = [0]
    captured_payloads = []

    def fake_post(url, json=None, timeout=None):
        call_count[0] += 1
        captured_payloads.append(json)
        return resp_413  # Always 413

    class SyncThread:
        def __init__(self, target=None, daemon=None, **kwargs):
            self._target = target
        def start(self):
            if self._target:
                self._target()

    original_max = sm_module._WEBHOOK_RETRY_MAX
    sm_module._WEBHOOK_RETRY_MAX = 3
    try:
        with patch("src.session_manager.requests.post", side_effect=fake_post), \
             patch("src.session_manager.time.sleep"), \
             patch("src.session_manager.threading.Thread", SyncThread):
            sm.get_or_create("sess-double-413")
            sm.set_callback("sess-double-413", "http://localhost:9999/cb", None)
            sm.store_result("sess-double-413", {
                "success": True,
                "report": "done",
                "output_files_content": [{"name": "f.mp4", "content_base64": "AAA", "mime": "video/mp4"}],
            })
    finally:
        sm_module._WEBHOOK_RETRY_MAX = original_max

    sm.cleanup_session("sess-double-413")

    # With max_attempts=3 and one free reset on 413:
    # attempt 0->1: 413, strip+reset to 0
    # attempt 0->1: 413 (stripped_on_413=True), backoff
    # attempt 1->2: 413 (stripped_on_413=True), backoff
    # attempt 2->3: 413 (stripped_on_413=True), exhausted -> return
    # Total = 4 calls (1 before reset + 3 after)
    assert call_count[0] == 4, (
        f"Expected 4 total calls (1 pre-strip + 3 post-strip exhaustion), got {call_count[0]}"
    )

    # The second call onward should have output_files_content_dropped=True but NO output_files_content
    for i, p in enumerate(captured_payloads[1:], start=2):
        result = p.get("result") or {}
        assert "output_files_content" not in result, (
            f"Call {i} must not have output_files_content (strip happened only once)"
        )
        assert result.get("output_files_content_dropped") is True, (
            f"Call {i} must have output_files_content_dropped=True"
        )
