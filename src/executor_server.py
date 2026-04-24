import io
import os
import subprocess
import sys
import traceback

from flask import Flask, request, jsonify

from src.logger import get_logger

logger = get_logger("executor-server")


def create_executor_app() -> Flask:
    app = Flask(__name__)
    workdir_base = os.getenv("WORKDIR_BASE", "/tmp/work")

    @app.post("/bash")
    def bash():
        data = request.get_json(force=True)
        command = data.get("command", "")
        session_id = data.get("session_id", "default")
        workdir = os.path.join(workdir_base, session_id)
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
        workdir = os.path.join(workdir_base, session_id)
        os.makedirs(workdir, exist_ok=True)
        logger.info("Executing python", extra={"session_id": session_id, "code": code[:200]})
        output_buffer = io.StringIO()
        try:
            # Redirect stdout/stderr to capture prints
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = output_buffer
            sys.stderr = output_buffer
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
            sys.stdout = old_stdout
            sys.stderr = old_stderr
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
