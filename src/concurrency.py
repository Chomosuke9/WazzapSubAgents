"""Global concurrency gate for sub-agent execution.

At most ``SUBAGENT_GLOBAL_LIMIT`` (default 1) sessions may run their agent
loop at a time. Additional sessions are held in a FIFO queue *before* any
LLM call or container tool execution happens, so waiting sessions cost
nothing but a blocked thread.

Callers wrap their work with :meth:`SubAgentQueue.acquire` /
:meth:`SubAgentQueue.release` (typically in a ``try``/``finally``). While
waiting, two callbacks let the caller emit webhooks so the bridge can
inform the end user about their position in line:

- ``on_enqueue(session_id, position, queue_size)`` — fired exactly once
  per session that actually has to wait (i.e. was not granted a slot
  immediately).
- ``on_advance(updates)`` — fired after this session finally acquires a
  slot, with one ``(session_id, new_position, queue_size)`` tuple for
  each *other* session still waiting behind.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, List, Optional, Tuple


@dataclass
class QueueEntry:
  session_id: str
  enqueued_at: float = field(default_factory=time.time)


QueueUpdate = Tuple[str, int, int]  # (session_id, position, queue_size)


class SubAgentQueue:
  """FIFO-ordered gate limiting concurrent sub-agent executions.

  The underlying primitive is a ``threading.Condition``: we keep an
  explicit deque of :class:`QueueEntry` so we can (a) hand out slots in
  strict FIFO order (``threading.Semaphore`` makes no such guarantee on
  CPython) and (b) snapshot the positions of waiting sessions when the
  queue advances.
  """

  def __init__(self, limit: Optional[int] = None) -> None:
    if limit is None:
      limit = int(os.getenv("SUBAGENT_GLOBAL_LIMIT", "1"))
    # Hardening: a zero/negative limit would deadlock; clamp to 1.
    limit = max(1, int(limit))
    self._limit = limit
    self._free = limit
    self._cond = threading.Condition()
    self._queue: Deque[QueueEntry] = deque()

  @property
  def limit(self) -> int:
    return self._limit

  def snapshot(self) -> List[QueueUpdate]:
    """Return ``(session_id, 1-based position, queue_size)`` for each
    currently-waiting entry. Primarily for tests/introspection."""
    with self._cond:
      total = len(self._queue)
      return [(entry.session_id, idx + 1, total) for idx, entry in enumerate(self._queue)]

  def acquire(
    self,
    session_id: str,
    on_enqueue: Optional[Callable[[str, int, int], None]] = None,
    on_advance: Optional[Callable[[List[QueueUpdate]], None]] = None,
  ) -> None:
    """Block until this session owns one of ``limit`` slots.

    See the module docstring for semantics of ``on_enqueue`` /
    ``on_advance``. Both callbacks are invoked while ``self._cond`` is
    held; :meth:`SessionManager._fire_webhook` is already non-blocking
    (spawns a daemon thread), so this is safe.
    """
    entry = QueueEntry(session_id=session_id)
    emitted_enqueue = False
    with self._cond:
      self._queue.append(entry)
      while True:
        if self._queue and self._queue[0] is entry and self._free > 0:
          self._queue.popleft()
          self._free -= 1
          remaining = [
            (e.session_id, i + 1, len(self._queue))
            for i, e in enumerate(self._queue)
          ]
          # Only broadcast advances if this session actually had to wait —
          # a session that was granted a slot instantly did not cause
          # anybody else's position to change.
          if emitted_enqueue and on_advance is not None and remaining:
            try:
              on_advance(remaining)
            except Exception:
              # Webhook failure must never deadlock the queue.
              pass
          return

        if not emitted_enqueue:
          position = next((i + 1 for i, e in enumerate(self._queue) if e is entry), 0)
          queue_size = len(self._queue)
          emitted_enqueue = True
          if on_enqueue is not None:
            try:
              on_enqueue(session_id, position, queue_size)
            except Exception:
              pass

        self._cond.wait()

  def release(self) -> None:
    """Return the slot held by the current session. Safe to call even if
    ``acquire`` raised mid-flight (in which case it is a no-op that
    merely re-notifies waiters in case they were stuck)."""
    with self._cond:
      if self._free < self._limit:
        self._free += 1
      self._cond.notify_all()


# Process-global singleton. Tests may instantiate their own SubAgentQueue.
_global_queue: Optional[SubAgentQueue] = None
_global_queue_lock = threading.Lock()


def get_global_queue() -> SubAgentQueue:
  global _global_queue
  with _global_queue_lock:
    if _global_queue is None:
      _global_queue = SubAgentQueue()
    return _global_queue
