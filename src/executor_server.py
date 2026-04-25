import io
import os
import subprocess
import sys
import threading
import traceback

from flask import Flask, request, jsonify

from src.logger import get_logger

logger = get_logger("executor-server")

# Guards the global stdout/stderr swap done while exec()-ing user code.
# Two concurrent /python requests would otherwise share the same redirected
# stdout buffer and the first one to finish would restore stdout out from
# under the other, garbling captured output.
_PY_EXEC_LOCK = threading.Lock()


def create_executor_app() -> Flask:
    app = Flask(__name__)
    workdir_base = os.getenv("WORKDIR_BASE", "/tmp/work")

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
        try:
            workdir = _resolve_workdir(session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        os.makedirs(workdir, exist_ok=True)
        logger.info("Executing bash", extra={"session_id": session_id, "command": command[:200]})
        result = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            shell=True,
            text=True,
            timeout=300,
        )
        return jsonify({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        })

    @app.post("/python")
    def python():
        data = request.get_json(force=True)
        code = data.get("code", "")
        session_id = data.get("session_id", "default")
        try:
            workdir = _resolve_workdir(session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        os.makedirs(workdir, exist_ok=True)
        logger.info("Executing python", extra={"session_id": session_id, "code": code[:200]})
        # Serialize exec() because we redirect process-global stdout/stderr.
        # Without this lock, concurrent requests step on each other's buffer.
        with _PY_EXEC_LOCK:
            output_buffer = io.StringIO()
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = output_buffer
            sys.stderr = output_buffer
            try:
                exec_globals = {
                    "__builtins__": __builtins__,
                    "sys": sys,
                    "os": os,
                    "io": io,
                    "json": __import__("json"),
                    "math": __import__("math"),
                    "re": __import__("re"),
                    "datetime": __import__("datetime"),
                }
                exec(code, exec_globals)
            except Exception:
                error_text = traceback.format_exc()
                return jsonify({"error": error_text})
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
        return jsonify({"output": output_buffer.getvalue()})

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5001"))
    app = create_executor_app()
    app.run(host="0.0.0.0", port=port, debug=False)
