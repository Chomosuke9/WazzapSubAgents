import os
import subprocess

from flask import Flask, request, jsonify

from src.logger import get_logger

logger = get_logger("executor-server")


def create_executor_app() -> Flask:
    app = Flask(__name__)
    workdir_base = os.getenv("WORKDIR_BASE", "/storage/subagent_work")

    def _resolve_workdir(session_id: str) -> str:
        """Resolve the per-session workdir, applying the same sanitization
        as ``SessionManager.get_or_create`` so the path used here matches
        the path the main service collects ``output_files`` from.

        Without this, a ``session_id`` like ``"/foo"`` would make the main
        service write to ``<workdir_base>/foo`` (lstrip-then-join) while
        ``os.path.join`` here would discard ``workdir_base`` entirely and
        write to ``/foo`` — silently losing every tool's output.
        """
        safe = session_id.lstrip(os.sep)
        real_base = os.path.realpath(workdir_base)
        resolved = os.path.realpath(os.path.join(real_base, safe))
        if resolved != real_base and not resolved.startswith(real_base + os.sep):
            raise ValueError(
                f"Invalid session_id {session_id!r}: resolves outside workdir_base"
            )
        if resolved == real_base:
            raise ValueError(
                f"Invalid session_id {session_id!r}: must not be empty"
            )
        return resolved

    @app.post("/bash")
    def bash():
        data = request.get_json(force=True)
        command = data.get("command", "")
        session_id = data.get("session_id", "default")
        timeout = data.get("timeout", 10)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = 10
        try:
            workdir = _resolve_workdir(session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        os.makedirs(workdir, exist_ok=True)
        logger.info("Executing bash", extra={"session_id": session_id, "command": command[:200], "timeout": timeout})
        try:
            result = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                shell=True,
                text=True,
                timeout=timeout,
            )
            return jsonify({
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            return jsonify({"error": f"Bash execution timed out ({timeout}s)"}), 200

    @app.post("/javascript")
    def javascript():
        data = request.get_json(force=True)
        code = data.get("code", "")
        session_id = data.get("session_id", "default")
        timeout = data.get("timeout", 10)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = 10
        try:
            workdir = _resolve_workdir(session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        os.makedirs(workdir, exist_ok=True)
        logger.info("Executing javascript", extra={"session_id": session_id, "code": code[:200], "timeout": timeout})

        # Write code to a temporary file to avoid shell escaping issues with complex scripts
        js_file = os.path.join(workdir, f".tmp_script_{os.getpid()}.js")
        try:
            with open(js_file, "w") as f:
                f.write(code)

            result = subprocess.run(
                ["node", js_file],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return jsonify({
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            return jsonify({"error": f"Javascript execution timed out ({timeout}s)"}), 200
        except Exception as e:
            logger.error("Javascript execution failed", exc_info=True)
            return jsonify({"error": str(e)}), 500
        finally:
            if os.path.exists(js_file):
                os.remove(js_file)

    @app.post("/python")
    def python():
        data = request.get_json(force=True)
        code = data.get("code", "")
        session_id = data.get("session_id", "default")
        timeout = data.get("timeout", 10)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = 10
        try:
            workdir = _resolve_workdir(session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        os.makedirs(workdir, exist_ok=True)
        logger.info("Executing python", extra={"session_id": session_id, "code": code[:200], "timeout": timeout})

        # Execute Python code in a subprocess so that memory-hungry code
        # (e.g. PyTorch model loading) cannot OOM-kill the Flask server.
        # This mirrors how /javascript and /bash already spawn child processes.
        py_file = os.path.join(workdir, f".tmp_script_{os.getpid()}.py")
        try:
            with open(py_file, "w") as f:
                f.write(code)

            result = subprocess.run(
                ["python3", py_file],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return jsonify({
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            return jsonify({"error": f"Python execution timed out ({timeout}s)"}), 200
        except Exception as e:
            logger.error("Python execution failed", exc_info=True)
            return jsonify({"error": str(e)}), 500
        finally:
            if os.path.exists(py_file):
                os.remove(py_file)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5001"))
    app = create_executor_app()
    app.run(host="0.0.0.0", port=port, debug=False)
