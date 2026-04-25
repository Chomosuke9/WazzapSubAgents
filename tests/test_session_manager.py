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
