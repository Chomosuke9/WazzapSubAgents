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
