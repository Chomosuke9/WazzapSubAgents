"""
Quick integration test for webhook push notification feature.
No external HTTP server needed -- we monkeypatch _fire_webhook to collect payloads.
"""
import json
import time
from unittest.mock import MagicMock

from src.session_manager import SessionManager


def test_webhook_flow():
    sm = SessionManager(idle_timeout=60)
    session = sm.get_or_create("test-session-1")

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
    import threading
    from unittest.mock import patch, MagicMock
    import requests as req_module

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


def test_413_fallback_resets_attempt_counter():
    """After 413 fallback, attempt counter resets so stripped payload gets full retries."""
    import threading
    import src.session_manager as sm_module
    from unittest.mock import patch, MagicMock
    import requests as req_module

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
