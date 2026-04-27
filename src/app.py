import threading
import time
from typing import Any, Dict

from flask import Flask, request, jsonify

from src.agent import ExecutorAgent
from src.concurrency import SubAgentQueue, get_global_queue
from src.config import config
from src.container_client import ContainerClient
from src.docker_manager import DockerManager
from src.input_staging import stage_inputs_into_workdir
from src.logger import get_logger
from src.session_manager import SessionManager

logger = get_logger(__name__)


def create_app(
    docker_mgr: DockerManager,
    queue: SubAgentQueue | None = None,
) -> Flask:
    app = Flask(__name__)
    container_url = docker_mgr.get_container_url()
    container_client = ContainerClient(container_url)
    session_manager = SessionManager(idle_timeout=config["session_idle_timeout"])
    # Global FIFO gate limiting concurrent agent executions (default 1).
    # Tests may inject a dedicated queue to avoid leaking process-global
    # state between cases.
    subagent_queue = queue if queue is not None else get_global_queue()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/execute")
    def execute():
        data = request.get_json(force=True)
        session_id = data.get("session_id")
        instruction = data.get("instruction")
        input_files = data.get("input_files", [])
        callback_url = data.get("callback_url")
        progress_webhook = data.get("progress_webhook")

        if not session_id or not instruction:
            return jsonify({"success": False, "report": "Missing session_id or instruction"}), 400

        try:
            session = session_manager.get_or_create(session_id)
        except ValueError as exc:
            # SessionManager.get_or_create raises ValueError for session_ids
            # that fail path-traversal validation (``..``, empty, dot-only).
            # Surface as 400 — this is a client validation failure, not a
            # server fault, so callers should not retry.
            logger.warning(
                "Rejected /execute: invalid session_id",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return jsonify({"success": False, "report": str(exc)}), 400
        session_manager.set_callback(session_id, callback_url, progress_webhook)

        # Re-stage the caller's input files into ``<workdir>/input/`` so the
        # paths handed to the agent's bash/python tools are reachable from
        # inside the executor sidecar. Without this, paths that live outside
        # the container's bind-mounts (e.g. WazzapAgents' default
        # ``<repo>/data/subagent_in/...``) appear as "file not found" and
        # the sub-agent loops searching ``/tmp /home /workspace /mnt /var``
        # before failing. ``workdir`` is rooted in ``WORKDIR_BASE`` which is
        # bind-mounted at the same host/container path, so the copies are
        # always visible inside the container.
        if input_files:
            staged_inputs = stage_inputs_into_workdir(session.workdir, input_files)
            logger.info(
                "Staged input files into workdir",
                extra={
                    "session_id": session_id,
                    "workdir": session.workdir,
                    "input_count": len(input_files),
                    "staged_count": len(staged_inputs),
                },
            )
            input_files = staged_inputs

        def _emit_queued(sid: str, position: int, queue_size: int) -> None:
            session_manager.fire_queue_event(
                sid,
                {
                    "type": "queued",
                    "session_id": sid,
                    "position": position,
                    "queue_size": queue_size,
                },
            )
            logger.info(
                "Session queued",
                extra={"session_id": sid, "position": position, "queue_size": queue_size},
            )

        def _emit_advance(updates: list[tuple[str, int, int]]) -> None:
            for sid, position, queue_size in updates:
                session_manager.fire_queue_event(
                    sid,
                    {
                        "type": "queue_advanced",
                        "session_id": sid,
                        "position": position,
                        "queue_size": queue_size,
                    },
                )
            logger.info(
                "Queue advanced",
                extra={"updates": [(sid, pos, qsize) for sid, pos, qsize in updates]},
            )

        def run_agent():
            acquired = False
            try:
                subagent_queue.acquire(
                    session_id,
                    on_enqueue=_emit_queued,
                    on_advance=_emit_advance,
                )
                acquired = True
                agent = ExecutorAgent(container_client, session_manager)
                result = agent.execute(
                    session_id=session_id,
                    instruction=instruction,
                    input_files=input_files,
                    workdir=session.workdir,
                )
                session_manager.store_result(session_id, result)
            except Exception as e:
                logger.error("Agent execution failed", extra={"session_id": session_id, "error": str(e)})
                session_manager.store_result(
                    session_id,
                    {
                        "session_id": session_id,
                        "success": False,
                        "report": f"Agent failed: {str(e)}",
                        "output_files": [],
                        "processing_time_sec": 0,
                    },
                )
            finally:
                # Semaphore release must run regardless of success / error /
                # timeout / cancel. If ``acquire`` itself raised before we
                # got a slot, we never incremented ``_free`` so there is
                # nothing to give back — ``release`` is a no-op in that
                # case.
                if acquired:
                    subagent_queue.release()

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()

        return jsonify({
            "status": "processing",
            "session_id": session_id,
            "message": "Agent starting...",
        }), 202

    @app.get("/sessions/<session_id>/result")
    def get_result(session_id: str):
        result = session_manager.get_result(session_id)
        if result is None:
            return jsonify({"success": False, "report": "Result not found or expired"}), 404
        return jsonify(result)

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"success": False, "report": "Bad request"}), 400

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"success": False, "report": "Internal server error"}), 500

    return app
