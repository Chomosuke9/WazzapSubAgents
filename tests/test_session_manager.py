import os
import time
from threading import Thread

from src.session_manager import SessionManager


def test_create_session():
    sm = SessionManager()
    session = sm.get_or_create("sess_1")
    assert session.session_id == "sess_1"
    assert os.path.isdir(session.workdir)
    # cleanup
    sm.cleanup_session("sess_1")


def test_get_existing_session():
    sm = SessionManager()
    s1 = sm.get_or_create("sess_2")
    s2 = sm.get_or_create("sess_2")
    assert s1 is s2
    sm.cleanup_session("sess_2")


def test_store_and_get_result():
    sm = SessionManager()
    sm.get_or_create("sess_3")
    sm.store_result("sess_3", {"success": True})
    assert sm.get_result("sess_3") == {"success": True}
    sm.cleanup_session("sess_3")


def test_result_not_found():
    sm = SessionManager()
    assert sm.get_result("nonexistent") is None


def test_cleanup_removes_workdir():
    sm = SessionManager()
    session = sm.get_or_create("sess_4")
    path = session.workdir
    sm.cleanup_session("sess_4")
    assert not os.path.exists(path)


def test_cleanup_thread():
    sm = SessionManager(idle_timeout=1)
    sm.get_or_create("sess_5")
    sm.store_result("sess_5", {"success": True})
    time.sleep(12)  # Wait for cleanup loop to run
    assert sm.get_result("sess_5") is None


def test_rejects_traversal_session_id(tmp_path, monkeypatch):
    # session_id is taken straight from the HTTP request body. ``..``
    # traversal must not be allowed to escape WORKDIR_BASE — otherwise
    # cleanup_session would shutil.rmtree an arbitrary directory.
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    sm = SessionManager()
    import pytest
    with pytest.raises(ValueError):
        sm.get_or_create("../../etc")
    with pytest.raises(ValueError):
        sm.get_or_create("..")
    with pytest.raises(ValueError):
        sm.get_or_create(".")
    with pytest.raises(ValueError):
        sm.get_or_create("")


def test_absolute_session_id_is_contained(tmp_path, monkeypatch):
    # An absolute-looking session_id like ``/etc`` must NOT escape
    # WORKDIR_BASE (the leading separator is stripped before joining).
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    sm = SessionManager()
    s = sm.get_or_create("/etc")
    assert s.workdir.startswith(str(tmp_path) + os.sep)
    sm.cleanup_session("/etc")


# ---------------------------------------------------------------------------
# Tests: output_files_content in webhook payload
# ---------------------------------------------------------------------------

import base64 as _base64


def test_store_result_includes_output_files_content(tmp_path, monkeypatch):
    """store_result must embed base64-encoded output_files_content in webhook."""
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    file_bytes = b"result-data-bytes"
    tmp_file = tmp_path / "output.txt"
    tmp_file.write_bytes(file_bytes)

    sm = SessionManager()
    sm.get_or_create("sess-out-content")
    sm.set_callback("sess-out-content", "http://localhost:9999/cb", None)

    captured = {}

    def _capture_webhook(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    sm._fire_webhook = _capture_webhook

    sm.store_result("sess-out-content", {
        "success": True,
        "report": "done",
        "output_files": [str(tmp_file)],
    })

    sm.cleanup_session("sess-out-content")

    assert "payload" in captured, "webhook was not fired"
    result = captured["payload"]["result"]
    assert "output_files_content" in result
    content_list = result["output_files_content"]
    assert isinstance(content_list, list)
    assert len(content_list) == 1
    entry = content_list[0]
    assert "name" in entry
    assert "content_base64" in entry
    assert "mime" in entry
    assert _base64.b64decode(entry["content_base64"]) == file_bytes


def test_store_result_omits_large_file_from_content(tmp_path, monkeypatch):
    """Files exceeding _MAX_INLINE_FILE_BYTES must be omitted from output_files_content."""
    import src.session_manager as sm_module
    monkeypatch.setenv("WORKDIR_BASE", str(tmp_path))
    monkeypatch.setattr(sm_module, "_MAX_INLINE_FILE_BYTES", 4)

    big_bytes = b"12345678"  # 8 bytes > 4 byte limit
    tmp_file = tmp_path / "big_output.bin"
    tmp_file.write_bytes(big_bytes)

    sm = SessionManager()
    sm.get_or_create("sess-large-out")
    sm.set_callback("sess-large-out", "http://localhost:9999/cb", None)

    captured = {}

    def _capture_webhook(url, payload):
        captured["payload"] = payload

    sm._fire_webhook = _capture_webhook

    sm.store_result("sess-large-out", {
        "success": True,
        "report": "ok",
        "output_files": [str(tmp_file)],
    })

    sm.cleanup_session("sess-large-out")

    assert "payload" in captured, "webhook was not fired"
    result = captured["payload"]["result"]
    # Large file must be absent from inlined content
    assert result["output_files_content"] == []
    # But the original path still present in output_files
    assert str(tmp_file) in result["output_files"]
