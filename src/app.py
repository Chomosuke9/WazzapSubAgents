import threading
import time
from typing import Any, Dict

from flask import Flask, request, jsonify

from src.agent import ExecutorAgent
from src.config import config
from src.container_client import ContainerClient
from src.docker_manager import DockerManager
from src.logger import get_logger
from src.session_manager import SessionManager

logger = get_logger(__name__)


def create_app(docker_mgr: DockerManager) -> Flask:
    app = Flask(__name__)
    container_url = docker_mgr.get_container_url()
    container_client = ContainerClient(container_url)
    session_manager = SessionManager(idle_timeout=config["session_idle_timeout"])

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

        session = session_manager.get_or_create(session_id)
        session_manager.set_callback(session_id, callback_url, progress_webhook)

        def run_agent():
            try:
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
