"""Tests for :mod:`src.concurrency` and its integration with
:class:`~src.session_manager.SessionManager`.

These tests pin the contract of the global sub-agent concurrency gate:

- at most ``limit`` sessions may hold a slot at once (limit=1 here);
- sessions acquire slots in strict FIFO order;
- webhooks are emitted only for sessions that had to wait, with the
  correct ``position`` / ``queue_size`` values;
- when a slot is released, every other session still waiting sees a
  ``queue_advanced`` broadcast with its updated position;
- the slot is released even if the protected work raises.
"""

from __future__ import annotations

import threading
import time
from typing import List, Tuple
from unittest.mock import patch

import pytest

from src.concurrency import SubAgentQueue
from src.session_manager import SessionManager


def _drain_thread(t: threading.Thread, timeout: float = 2.0) -> None:
  t.join(timeout=timeout)
  assert not t.is_alive(), "thread did not finish within timeout"


def test_single_session_acquires_immediately_without_webhook():
  queue = SubAgentQueue(limit=1)
  enqueues: list[tuple[str, int, int]] = []
  advances: list[list[tuple[str, int, int]]] = []

  queue.acquire(
    "sess-A",
    on_enqueue=lambda sid, pos, qs: enqueues.append((sid, pos, qs)),
    on_advance=lambda updates: advances.append(list(updates)),
  )

  assert enqueues == [], "solo session must not emit a 'queued' webhook"
  assert advances == [], "solo session has nobody behind it to advance"
  queue.release()


def test_three_sessions_fifo_with_queue_webhooks():
  queue = SubAgentQueue(limit=1)

  # Structured event log: each entry is (session_id, event_type, payload)
  events: list[tuple[str, str, tuple]] = []
  events_lock = threading.Lock()

  def enqueue_cb(sid: str) -> callable:
    def _cb(session_id, pos, qs):
      with events_lock:
        events.append((sid, "enqueue", (session_id, pos, qs)))
    return _cb

  def advance_cb(sid: str) -> callable:
    def _cb(updates):
      with events_lock:
        # Capture a tuple-of-tuples so tests can compare cleanly.
        events.append((sid, "advance", tuple(updates)))
    return _cb

  acquire_order: list[str] = []
  order_lock = threading.Lock()

  def worker(sid: str, hold: float = 0.15) -> None:
    queue.acquire(sid, on_enqueue=enqueue_cb(sid), on_advance=advance_cb(sid))
    with order_lock:
      acquire_order.append(sid)
    time.sleep(hold)
    queue.release()

  tA = threading.Thread(target=worker, args=("sess-A",))
  tA.start()
  # Give A time to grab the slot.
  time.sleep(0.05)

  tB = threading.Thread(target=worker, args=("sess-B",))
  tB.start()
  time.sleep(0.05)

  tC = threading.Thread(target=worker, args=("sess-C",))
  tC.start()
  time.sleep(0.05)

  for t in (tA, tB, tC):
    _drain_thread(t, timeout=5.0)

  # FIFO acquisition order.
  assert acquire_order == ["sess-A", "sess-B", "sess-C"], acquire_order

  # A never waited, so never emitted a queued webhook.
  enqueue_events = [e for e in events if e[1] == "enqueue"]
  enqueue_owners = [e[0] for e in enqueue_events]
  assert "sess-A" not in enqueue_owners

  # B joined while A was running → position 1, queue_size 1 (only B waiting).
  b_enq = [e[2] for e in enqueue_events if e[0] == "sess-B"]
  assert b_enq == [("sess-B", 1, 1)], b_enq

  # C joined while B was still queued and A still running → position 2,
  # queue_size 2 (B + C both waiting).
  c_enq = [e[2] for e in enqueue_events if e[0] == "sess-C"]
  assert c_enq == [("sess-C", 2, 2)], c_enq

  # When A releases, B acquires and must broadcast advance for C (now pos 1).
  advance_events = [e for e in events if e[1] == "advance"]
  b_adv = [e[2] for e in advance_events if e[0] == "sess-B"]
  assert b_adv == [(("sess-C", 1, 1),)], b_adv

  # When B releases, C acquires but there is nobody behind — no broadcast.
  c_adv = [e[2] for e in advance_events if e[0] == "sess-C"]
  assert c_adv == []


def test_release_runs_even_when_work_raises():
  queue = SubAgentQueue(limit=1)
  # First, take the slot via a worker that raises mid-flight but still
  # releases in a finally. This mirrors the ``run_agent`` wrapper in
  # ``src/app.py``.
  start = threading.Event()
  finished = threading.Event()

  def worker():
    queue.acquire("sess-boom")
    start.set()
    try:
      # Simulate an agent-loop error, caught here so the test thread does
      # not bubble an unhandled exception up to pytest. The real
      # ``run_agent`` wrapper in ``src/app.py`` does the same: catches the
      # error, records it as a failed result, and releases in ``finally``.
      try:
        raise RuntimeError("simulated agent failure")
      except RuntimeError:
        pass
    finally:
      queue.release()
      finished.set()

  t = threading.Thread(target=worker)
  t.start()
  start.wait(timeout=1.0)
  finished.wait(timeout=1.0)
  t.join(timeout=1.0)

  # Slot was released despite the raise — a follow-up acquire must not
  # block forever.
  acquired = threading.Event()

  def follow_up():
    queue.acquire("sess-after")
    acquired.set()
    queue.release()

  t2 = threading.Thread(target=follow_up)
  t2.start()
  assert acquired.wait(timeout=1.0), "queue did not release after exception"
  t2.join(timeout=1.0)


def test_fire_queue_event_uses_progress_webhook():
  """``SessionManager.fire_queue_event`` must dispatch to the session's
  configured ``progress_webhook`` — the bridge reuses the same webhook
  channel for queue events so it only has to run one HTTP server."""
  sm = SessionManager(idle_timeout=60)
  sm.get_or_create("sess-1")
  sm.set_callback("sess-1", None, "http://bridge/webhook")

  captured: list[tuple[str, dict]] = []
  sm._fire_webhook = lambda url, payload: captured.append((url, payload))

  sm.fire_queue_event("sess-1", {"type": "queued", "position": 1, "queue_size": 1})

  assert captured == [
    ("http://bridge/webhook", {"type": "queued", "position": 1, "queue_size": 1}),
  ]


def test_fire_queue_event_ignores_missing_webhook():
  sm = SessionManager(idle_timeout=60)
  sm.get_or_create("sess-silent")
  # No progress webhook configured.
  captured: list = []
  sm._fire_webhook = lambda url, payload: captured.append((url, payload))
  sm.fire_queue_event("sess-silent", {"type": "queued"})
  assert captured == []


def test_queue_survives_acquire_interruption():
  """If a waiter is interrupted (e.g. by a BaseException) while blocked in
  ``acquire()``, its queue entry must not deadlock every session behind it."""
  queue = SubAgentQueue(limit=1)

  # Occupy the sole slot.
  queue.acquire("sess-holder")

  class SimulatedInterrupt(BaseException):
    pass

  def interrupting_callback(*args):
    raise SimulatedInterrupt("simulated interrupt")

  def worker():
    try:
      queue.acquire("sess-doomed", on_enqueue=interrupting_callback)
    except SimulatedInterrupt:
      pass

  t = threading.Thread(target=worker)
  t.start()
  t.join(timeout=2.0)
  assert not t.is_alive(), "worker did not finish"

  # Release the slot.  A follow-up acquire must succeed — the zombie entry
  # left by ``sess-doomed`` must not block it forever.
  queue.release()

  acquired = threading.Event()

  def follow_up():
    queue.acquire("sess-after")
    acquired.set()
    queue.release()

  t2 = threading.Thread(target=follow_up)
  t2.start()
  assert acquired.wait(timeout=2.0), "queue deadlocked after interrupted acquire"
  t2.join(timeout=2.0)


def test_fire_queue_event_ignores_unknown_session():
  sm = SessionManager(idle_timeout=60)
  captured: list = []
  sm._fire_webhook = lambda url, payload: captured.append((url, payload))
  sm.fire_queue_event("no-such-session", {"type": "queued"})
  assert captured == []
