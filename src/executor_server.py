import hashlib
import hmac
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import nullcontext
from pathlib import Path
from typing import Callable

from flask import Flask, jsonify, request

from src.logger import get_logger
from src.tool_environment import TOOL_ENV_BLOCKLIST, parse_tool_env_passthrough

logger = get_logger("executor-server")

# Execution timeout upper bound — prevents a single request from holding a
# Flask thread for an unbounded amount of time.
MAX_TIMEOUT = 1800  # 30 minutes
DEFAULT_EXECUTION_TIMEOUT = 60
MAX_REQUEST_BYTES = int(os.getenv("EXECUTOR_MAX_REQUEST_BYTES", str(2 * 1024 * 1024)))
MAX_CACHED_RESULTS = int(os.getenv("EXECUTOR_MAX_CACHED_RESULTS", "1000"))
MAX_OUTPUT_BYTES = int(os.getenv("EXECUTOR_MAX_OUTPUT_BYTES", str(4 * 1024 * 1024)))
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._-]{0,199}$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{15,127}$")
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
REQUIRE_UID_ISOLATION = os.getenv(
    "EXECUTOR_REQUIRE_UID_ISOLATION", "1"
).strip().lower() not in {"0", "false", "no", "off"}
EXECUTOR_PARENT_UID = int(os.getenv("EXECUTOR_PARENT_UID", "0"))
if EXECUTOR_PARENT_UID < 0:
    raise ValueError("EXECUTOR_PARENT_UID must be zero or a positive integer")
TOOL_ENV_ALLOWLIST = {
    "PATH", "NODE_PATH", "LANG", "LC_ALL", "TZ",
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "SystemRoot", "SYSTEMROOT", "ComSpec", "COMSPEC", "PATHEXT", "WINDIR",
}
TOOL_ENV_PASSTHROUGH = {
    name.upper() for name in parse_tool_env_passthrough()
}
METHODS_MARKER = ".methods-root"
METHODS_MARKER_CONTENT = "wazzapsubagents-methods-v1"
DEPENDENCIES_MARKER = ".dependencies-root"
DEPENDENCIES_MARKER_CONTENT = "wazzapsubagents-dependencies-v1"


def _prepare_shared_methods_directory(methods_dir: str) -> bool:
    """Make learned method docs shareable by every isolated session UID.

    Session commands intentionally use a restrictive ``umask``. The executor
    therefore normalizes only the marked methods directory after each command;
    workdir permissions and cross-session isolation remain unchanged.
    """
    root = Path(methods_dir)
    try:
        marker = root / METHODS_MARKER
        if (
            not root.is_dir()
            or root.is_symlink()
            or marker.is_symlink()
            or not marker.is_file()
            or marker.read_text(encoding="utf-8").strip() != METHODS_MARKER_CONTENT
        ):
            return False
        os.chmod(root, 0o777)
        for candidate in root.iterdir():
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or candidate.suffix.lower() not in {".md", ".txt"}
            ):
                continue
            os.chmod(candidate, 0o666)
        return True
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning(
            "Methods directory permissions could not be normalized",
            extra={"methods_dir": str(root), "error": str(exc)},
        )
        return False


def _prepare_shared_dependencies_directory(dependencies_dir: str) -> bool:
    """Prepare a marked persistent dependency tree for all session UIDs."""
    root = Path(dependencies_dir)
    try:
        marker = root / DEPENDENCIES_MARKER
        if (
            not root.is_dir()
            or root.is_symlink()
            or marker.is_symlink()
            or not marker.is_file()
            or marker.read_text(encoding="utf-8").strip()
            != DEPENDENCIES_MARKER_CONTENT
        ):
            return False

        for name in ("python", "node", "bin", "cache"):
            (root / name).mkdir(exist_ok=True)

        directories: list[str] = []
        for current_root, dirs, files in os.walk(root, topdown=True, followlinks=False):
            if os.path.islink(current_root):
                dirs[:] = []
                continue
            dirs[:] = [
                name
                for name in dirs
                if not os.path.islink(os.path.join(current_root, name))
            ]
            os.chmod(current_root, 0o777)
            directories.append(current_root)
            for name in files:
                path = os.path.join(current_root, name)
                if os.path.islink(path):
                    continue
                executable = os.stat(path, follow_symlinks=False).st_mode & 0o111
                os.chmod(path, 0o666 | (0o111 if executable else 0))

        setfacl = shutil.which("setfacl")
        if os.name != "nt" and setfacl:
            acl = (
                "u::rwx,g::rwx,o::rwx,m::rwx,"
                "d:u::rwx,d:g::rwx,d:o::rwx,d:m::rwx"
            )
            for offset in range(0, len(directories), 128):
                subprocess.run(
                    [setfacl, "-m", acl, *directories[offset:offset + 128]],
                    check=True,
                    capture_output=True,
                    text=True,
                )
        return True
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        logger.warning(
            "Dependencies directory permissions could not be normalized",
            extra={"dependencies_dir": str(root), "error": str(exc)},
        )
        return False


def _may_modify_dependencies(source: str) -> bool:
    """Return whether a generated command may mutate persistent dependencies."""
    lowered = source.lower()
    if "/dependencies" in lowered:
        return True
    return bool(
        re.search(r"\b(?:pip3?|npm)\b[^\n]*(?:\binstall\b|\bi\b|\badd\b)", lowered)
    )


def _clamp_timeout(timeout, default: int = DEFAULT_EXECUTION_TIMEOUT) -> int | float:
    """Validate and clamp an execution timeout.

    Falls back to *default* when the value is missing, non-numeric,
    non-positive, or exceeds ``MAX_TIMEOUT``.
    """
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return default
    if timeout > MAX_TIMEOUT:
        return MAX_TIMEOUT
    return timeout


def _safe_remove(path: str) -> None:
    """Remove a temp file, ignoring OS errors so a cleanup failure never
    masks the real result of a tool execution."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        logger.warning("Failed to remove temp file %s: %s", path, exc)


def _write_session_script(path: str, source: str, isolation: dict) -> None:
    """Create a private script that the isolated session UID can read.

    The executor HTTP process runs as root so it can assign a distinct UID to
    each session. Creating a script with normal ``open()`` would therefore
    leave it owned by root; inherited ACLs or a restrictive parent umask can
    then make Python/Node fail while direct shell commands still work.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file_handle:
            descriptor = -1
            file_handle.write(source)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        if "user" in isolation and hasattr(os, "chown"):
            uid = int(isolation["user"])
            gid = int(isolation.get("group", uid))
            os.chown(path, uid, gid)
        os.chmod(path, 0o600)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        _safe_remove(path)
        raise


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass


def _run_bounded(
    command: str | list[str],
    *,
    workdir: str,
    timeout: int | float,
    isolation: dict,
) -> tuple[str, str, int, str | None]:
    """Run a command without unbounded pipes and kill its whole process group."""
    with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(
        mode="w+b"
    ) as stderr_file:
        options = dict(isolation)
        if os.name == "nt":
            options["creationflags"] = options.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        process = subprocess.Popen(
            command,
            cwd=workdir,
            stdout=stdout_file,
            stderr=stderr_file,
            text=False,
            **options,
        )
        deadline = time.monotonic() + timeout
        failure: str | None = None
        while process.poll() is None:
            output_size = os.fstat(stdout_file.fileno()).st_size + os.fstat(
                stderr_file.fileno()
            ).st_size
            if output_size > MAX_OUTPUT_BYTES:
                failure = f"Execution output exceeded {MAX_OUTPUT_BYTES} byte limit"
                _terminate_process_tree(process)
                break
            if time.monotonic() >= deadline:
                failure = f"Execution timed out ({timeout}s)"
                _terminate_process_tree(process)
                break
            time.sleep(0.02)
        try:
            returncode = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            returncode = process.wait(timeout=5)
        final_output_size = os.fstat(stdout_file.fileno()).st_size + os.fstat(
            stderr_file.fileno()
        ).st_size
        if failure is None and final_output_size >= MAX_OUTPUT_BYTES:
            failure = f"Execution output exceeded {MAX_OUTPUT_BYTES} byte limit"
        stdout_file.seek(0)
        stderr_file.seek(0)
        remaining = MAX_OUTPUT_BYTES
        stdout_bytes = stdout_file.read(remaining)
        remaining -= len(stdout_bytes)
        stderr_bytes = stderr_file.read(remaining)
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return stdout, stderr, returncode, failure


def create_executor_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    workdir_base = os.getenv("WORKDIR_BASE", "/storage/subagent_work")
    methods_dir = os.getenv("METHODS_DIR", "/methods")
    dependencies_dir = os.getenv("DEPENDENCIES_DIR", "/dependencies")
    bind_host = os.getenv("EXECUTOR_BIND_HOST", "127.0.0.1").strip()
    api_token = os.getenv("EXECUTOR_API_TOKEN", "").strip()
    require_auth = os.getenv("EXECUTOR_REQUIRE_AUTH", "1").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if require_auth and not api_token:
        raise RuntimeError(
            "EXECUTOR_API_TOKEN is required when EXECUTOR_REQUIRE_AUTH=1"
        )
    if not require_auth and bind_host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError(
            "Unauthenticated executor mode is allowed only on a loopback bind address"
        )
    result_lock = threading.RLock()
    dependency_lock = threading.RLock()
    result_cache: "OrderedDict[tuple[str, str, str], tuple[str, dict, int]]" = OrderedDict()
    in_flight: dict[tuple[str, str, str], tuple[str, threading.Event]] = {}
    uid_lock = threading.RLock()
    session_uids: dict[str, int] = {}
    used_uids: dict[int, str] = {}

    def _load_uid_secret() -> bytes:
        secret_path = os.path.join(workdir_base, ".executor_uid_secret")
        try:
            secret = Path(secret_path).read_bytes()
            if len(secret) == 32:
                return secret
        except OSError:
            pass
        secret = os.urandom(32)
        temporary = secret_path + f".{uuid.uuid4().hex}.tmp"
        with open(temporary, "wb") as file_handle:
            file_handle.write(secret)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, secret_path)
        return secret

    def _uid_signature(session_id: str, uid: int) -> str:
        return hmac.new(
            uid_secret,
            f"{session_id}\0{uid}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _load_uid_markers() -> None:
        if os.name == "nt" or not os.path.isdir(workdir_base):
            return
        try:
            entries = list(os.scandir(workdir_base))
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            marker = os.path.join(entry.path, ".executor_uid")
            try:
                raw = json.loads(Path(marker).read_text(encoding="ascii"))
                session_id = str(raw["session_id"])
                uid = int(raw["uid"])
                signature = str(raw["signature"])
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
            if (
                SESSION_ID_RE.fullmatch(session_id)
                and 100_000 <= uid <= 2_000_000_000
                and hmac.compare_digest(signature, _uid_signature(session_id, uid))
            ):
                session_uids[session_id] = uid
                used_uids[uid] = session_id

    def _allocate_session_uid(session_id: str, workdir: str) -> int:
        with uid_lock:
            existing = session_uids.get(session_id)
            if existing is not None:
                return existing
            candidate = 100_000 + (
                int.from_bytes(hashlib.sha256(session_id.encode("utf-8")).digest()[:4], "big")
                % 1_999_900_001
            )
            while (
                candidate == EXECUTOR_PARENT_UID
                or (candidate in used_uids and used_uids[candidate] != session_id)
            ):
                candidate += 1
                if candidate > 2_000_000_000:
                    candidate = 100_000
            session_uids[session_id] = candidate
            used_uids[candidate] = session_id
            marker = os.path.join(workdir, ".executor_uid")
            temporary = marker + f".{uuid.uuid4().hex}.tmp"
            with open(temporary, "w", encoding="ascii") as file_handle:
                json.dump({
                    "session_id": session_id,
                    "uid": candidate,
                    "signature": _uid_signature(session_id, candidate),
                }, file_handle)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temporary, marker)
            return candidate

    def _prepare_session_isolation(session_id: str, workdir: str) -> dict:
        """Give every session a distinct Unix UID and private 0700 tree."""
        temp_dir = os.path.join(workdir, ".tmp")
        os.makedirs(temp_dir, mode=0o700, exist_ok=True)
        tool_env = {
            key: value
            for key, value in os.environ.items()
            if (
                key in TOOL_ENV_ALLOWLIST or key.upper() in TOOL_ENV_PASSTHROUGH
            ) and key.upper() not in TOOL_ENV_BLOCKLIST
        }
        dependency_python = os.path.join(dependencies_dir, "python")
        dependency_python_bin = os.path.join(dependency_python, "bin")
        dependency_node = os.path.join(dependencies_dir, "node")
        dependency_node_modules = os.path.join(dependency_node, "node_modules")
        dependency_bin = os.path.join(dependencies_dir, "bin")
        dependency_node_bin = os.path.join(dependency_node_modules, ".bin")
        dependency_cache = os.path.join(dependencies_dir, "cache")
        runtime_path = os.pathsep.join(
            part
            for part in (
                dependency_bin,
                dependency_python_bin,
                dependency_node_bin,
                tool_env.get("PATH", os.defpath),
            )
            if part
        )
        node_path = os.pathsep.join(
            part
            for part in (
                dependency_node_modules,
                tool_env.get("NODE_PATH", ""),
            )
            if part
        )
        tool_env.update({
            "HOME": workdir,
            "USER": "subagent",
            "LOGNAME": "subagent",
            "TMPDIR": temp_dir,
            "TMP": temp_dir,
            "TEMP": temp_dir,
            "PATH": runtime_path,
            "PYTHONPATH": dependency_python,
            "PIP_TARGET": dependency_python,
            "PIP_CACHE_DIR": os.path.join(dependency_cache, "pip"),
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "NODE_PATH": node_path,
            "NPM_CONFIG_PREFIX": dependency_node,
            "NPM_CONFIG_CACHE": os.path.join(dependency_cache, "npm"),
        })
        if os.name == "nt" or not REQUIRE_UID_ISOLATION:
            return {"env": tool_env}
        if not hasattr(os, "geteuid") or os.geteuid() != 0:
            raise RuntimeError(
                "Executor requires root to isolate session UIDs; set "
                "EXECUTOR_REQUIRE_UID_ISOLATION=0 only in a trusted single-session environment"
            )
        uid = _allocate_session_uid(session_id, workdir)
        os.chmod(workdir_base, 0o711)
        for current_root, dirs, files in os.walk(workdir, followlinks=False):
            if os.path.islink(current_root):
                raise RuntimeError("Session workdir contains a symlinked directory")
            os.chown(current_root, uid, uid)
            os.chmod(current_root, 0o700)
            for name in dirs:
                path = os.path.join(current_root, name)
                if os.path.islink(path):
                    os.unlink(path)
                    continue
                os.chown(path, uid, uid)
                os.chmod(path, 0o700)
            for name in files:
                path = os.path.join(current_root, name)
                if os.path.islink(path):
                    os.unlink(path)
                    continue
                original_mode = os.stat(path, follow_symlinks=False).st_mode
                os.chown(path, uid, uid)
                executable = original_mode & 0o111
                os.chmod(path, 0o600 | executable)
        os.chown(temp_dir, uid, uid)
        os.chmod(temp_dir, 0o700)
        isolated_stat = os.stat(workdir, follow_symlinks=False)
        if isolated_stat.st_uid != uid or (isolated_stat.st_mode & 0o077):
            raise RuntimeError(
                "WORKDIR_BASE filesystem does not enforce required UID/mode isolation"
            )
        if EXECUTOR_PARENT_UID not in {0, uid}:
            # The host service commonly runs as a non-root user on Linux.
            # Preserve that user's access without granting it to sibling
            # session UIDs. Default ACLs cover files created by later commands.
            for current_root, dirs, files in os.walk(workdir, followlinks=False):
                subprocess.run(
                    [
                        "setfacl", "-m",
                        f"u:{EXECUTOR_PARENT_UID}:rwx,d:u:{EXECUTOR_PARENT_UID}:rwx",
                        current_root,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                for name in files:
                    subprocess.run(
                        [
                            "setfacl", "-m",
                            f"u:{EXECUTOR_PARENT_UID}:rw",
                            os.path.join(current_root, name),
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
        return {
            "user": uid,
            "group": uid,
            "extra_groups": [],
            "umask": 0o077,
            "env": tool_env,
        }

    os.makedirs(workdir_base, exist_ok=True)
    if not _prepare_shared_methods_directory(methods_dir):
        logger.warning(
            "Shared methods directory is unavailable or missing its marker",
            extra={"methods_dir": methods_dir},
        )
    if not _prepare_shared_dependencies_directory(dependencies_dir):
        logger.warning(
            "Shared dependencies directory is unavailable or missing its marker",
            extra={"dependencies_dir": dependencies_dir},
        )
    uid_secret = _load_uid_secret()
    _load_uid_markers()

    @app.before_request
    def _authenticate_execution_request():
        if request.path not in {"/bash", "/python", "/javascript"}:
            return None
        if not api_token:
            return None
        authorization = request.headers.get("Authorization", "")
        supplied = (
            authorization[7:].strip()
            if authorization.lower().startswith("bearer ")
            else request.headers.get("X-Executor-Token", "").strip()
        )
        if not supplied or not hmac.compare_digest(supplied, api_token):
            return jsonify({"error": "Unauthorized executor request"}), 401
        return None

    def _atomic_json(path: str, value: dict) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = f"{path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as file_handle:
                json.dump(value, file_handle, ensure_ascii=False)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temporary, path)
        finally:
            _safe_remove(temporary)

    def _resolve_workdir(session_id: str) -> str:
        """Resolve the per-session workdir, applying the same sanitization
        as ``SessionManager.get_or_create`` so the path used here matches
        the path the main service collects ``output_files`` from.

        Without this, a ``session_id`` like ``"/foo"`` would make the main
        service write to ``<workdir_base>/foo`` (lstrip-then-join) while
        ``os.path.join`` here would discard ``workdir_base`` entirely and
        write to ``/foo`` — silently losing every tool's output.
        """
        if not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
            raise ValueError(
                "Invalid session_id: use 1-200 letters, digits, @, dot, underscore, or hyphen"
            )
        if session_id.endswith(".") or session_id.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise ValueError("Invalid session_id: reserved or filesystem-ambiguous name")
        safe = session_id
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

    def _request_data(required_field: str) -> tuple[dict, str, str, int | float] | tuple[None, dict, int]:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return None, {"error": "Request body must be a JSON object"}, 400
        source = data.get(required_field)
        if not isinstance(source, str) or not source:
            return None, {"error": f"{required_field} must be a non-empty string"}, 400
        session_id = data.get("session_id", "default")
        try:
            workdir = _resolve_workdir(session_id)
        except ValueError as exc:
            return None, {"error": str(exc)}, 400
        request_id = data.get("request_id") or uuid.uuid4().hex
        if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
            return None, {"error": "request_id must be 16-128 URL-safe characters"}, 400
        timeout = _clamp_timeout(data.get("timeout", DEFAULT_EXECUTION_TIMEOUT))
        return data, workdir, request_id, timeout

    def _execute_idempotently(
        workdir: str,
        operation_name: str,
        request_id: str,
        fingerprint: str,
        operation: Callable[[], tuple[dict, int]],
    ) -> tuple[dict, int]:
        """Execute one request id once, sharing its result with retries."""
        key = (workdir, operation_name, request_id)
        cache_dir = os.path.join(workdir, ".executor_results")
        cache_name = hashlib.sha256(
            f"{operation_name}\0{request_id}".encode("utf-8")
        ).hexdigest() + ".json"
        cache_path = os.path.join(cache_dir, cache_name)

        try:
            with open(cache_path, "r", encoding="utf-8") as file_handle:
                durable = json.load(file_handle)
        except FileNotFoundError:
            durable = None
        except (OSError, ValueError, TypeError) as exc:
            logger.error(
                "Executor receipt is unreadable; refusing possible re-execution",
                extra={"request_id": request_id, "error": str(exc)},
            )
            return {"error": "Executor receipt is unreadable; refusing to execute again"}, 503
        if durable is not None:
            if not isinstance(durable, dict) or durable.get("fingerprint") != fingerprint:
                return {"error": "request_id is already bound to different input"}, 409
            state = durable.get("state")
            if state == "running":
                return {"error": "Previous execution outcome is indeterminate; refusing to execute it again"}, 503
            if (
                state != "complete"
                or not isinstance(durable.get("payload"), dict)
                or isinstance(durable.get("status"), bool)
                or not isinstance(durable.get("status"), int)
            ):
                return {"error": "Executor receipt is invalid; refusing to execute again"}, 503
            return durable["payload"], durable["status"]

        owner = False
        with result_lock:
            cached = result_cache.get(key)
            if cached is not None:
                result_cache.move_to_end(key)
                if cached[0] != fingerprint:
                    return {"error": "request_id is already bound to different input"}, 409
                return cached[1], cached[2]
            flight = in_flight.get(key)
            if flight is None:
                event = threading.Event()
                in_flight[key] = (fingerprint, event)
                owner = True
            else:
                active_fingerprint, event = flight
                if active_fingerprint != fingerprint:
                    return {"error": "request_id is already bound to different input"}, 409

        if not owner:
            if not event.wait(MAX_TIMEOUT + 30):
                return {"error": "Duplicate request is still running"}, 409
            with result_lock:
                cached = result_cache.get(key)
                if cached is None:
                    return {"error": "Original request failed before producing a result"}, 503
                result_cache.move_to_end(key)
                return cached[1], cached[2]

        try:
            try:
                _atomic_json(
                    cache_path,
                    {"fingerprint": fingerprint, "state": "running"},
                )
            except OSError as exc:
                logger.error(
                    "Refusing execution because idempotency claim could not be persisted",
                    extra={"request_id": request_id, "error": str(exc)},
                )
                return {"error": "Executor receipt storage is unavailable"}, 503
            response = operation()
            try:
                _atomic_json(
                    cache_path,
                    {
                        "fingerprint": fingerprint,
                        "state": "complete",
                        "payload": response[0],
                        "status": response[1],
                    },
                )
            except OSError as exc:
                logger.error(
                    "Executor completed but its result receipt could not be persisted",
                    extra={"request_id": request_id, "error": str(exc)},
                )
                with result_lock:
                    result_cache[key] = (fingerprint, response[0], response[1])
                    result_cache.move_to_end(key)
                return {"error": "Execution completed but its durable receipt is unavailable"}, 503
            with result_lock:
                result_cache[key] = (fingerprint, response[0], response[1])
                result_cache.move_to_end(key)
                while len(result_cache) > MAX_CACHED_RESULTS:
                    result_cache.popitem(last=False)
            return response
        finally:
            with result_lock:
                in_flight.pop(key, None)
                event.set()

    @app.post("/bash")
    def bash():
        parsed = _request_data("command")
        if parsed[0] is None:
            _, error, status = parsed
            return jsonify(error), status
        data, workdir, request_id, timeout = parsed
        command = data["command"]
        fingerprint = hashlib.sha256(
            json.dumps({"command": command, "timeout": timeout}, sort_keys=True).encode("utf-8")
        ).hexdigest()
        session_id = data.get("session_id", "default")
        os.makedirs(workdir, exist_ok=True)
        try:
            isolation = _prepare_session_isolation(session_id, workdir)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            logger.error("Session isolation failed", extra={"session_id": session_id, "error": str(exc)})
            return jsonify({"error": str(exc), "request_id": request_id}), 503
        logger.info("Executing bash", extra={"session_id": session_id, "command": command[:200], "timeout": timeout})

        def operation() -> tuple[dict, int]:
            dependency_mutation = _may_modify_dependencies(command)
            lock = dependency_lock if dependency_mutation else nullcontext()
            with lock:
                try:
                    stdout, stderr, returncode, failure = _run_bounded(
                        command,
                        workdir=workdir,
                        timeout=timeout,
                        isolation={**isolation, "shell": True},
                    )
                    if failure:
                        return {"error": f"Bash {failure.lower()}", "request_id": request_id}, 200
                    return {
                        "stdout": stdout,
                        "stderr": stderr,
                        "returncode": returncode,
                        "request_id": request_id,
                    }, 200
                except Exception as exc:
                    logger.error("Bash execution failed", exc_info=True)
                    return {"error": str(exc), "request_id": request_id}, 500
                finally:
                    _prepare_shared_methods_directory(methods_dir)
                    if dependency_mutation:
                        _prepare_shared_dependencies_directory(dependencies_dir)

        payload, status = _execute_idempotently(workdir, "bash", request_id, fingerprint, operation)
        return jsonify(payload), status

    @app.post("/javascript")
    def javascript():
        parsed = _request_data("code")
        if parsed[0] is None:
            _, error, status = parsed
            return jsonify(error), status
        data, workdir, request_id, timeout = parsed
        code = data["code"]
        fingerprint = hashlib.sha256(
            json.dumps({"code": code, "timeout": timeout}, sort_keys=True).encode("utf-8")
        ).hexdigest()
        session_id = data.get("session_id", "default")
        os.makedirs(workdir, exist_ok=True)
        try:
            isolation = _prepare_session_isolation(session_id, workdir)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            logger.error("Session isolation failed", extra={"session_id": session_id, "error": str(exc)})
            return jsonify({"error": str(exc), "request_id": request_id}), 503
        logger.info("Executing javascript", extra={"session_id": session_id, "code": code[:200], "timeout": timeout})

        def operation() -> tuple[dict, int]:
            js_file = os.path.join(
                isolation["env"]["TMPDIR"],
                f"script-{uuid.uuid4().hex}.js",
            )
            dependency_mutation = _may_modify_dependencies(code)
            lock = dependency_lock if dependency_mutation else nullcontext()
            with lock:
                try:
                    _write_session_script(js_file, code, isolation)
                    stdout, stderr, returncode, failure = _run_bounded(
                        ["node", js_file],
                        workdir=workdir,
                        timeout=timeout,
                        isolation=isolation,
                    )
                    if failure:
                        return {"error": f"Javascript {failure.lower()}", "request_id": request_id}, 200
                    return {
                        "stdout": stdout,
                        "stderr": stderr,
                        "returncode": returncode,
                        "request_id": request_id,
                    }, 200
                except Exception as exc:
                    logger.error("Javascript execution failed", exc_info=True)
                    return {"error": str(exc), "request_id": request_id}, 500
                finally:
                    _safe_remove(js_file)
                    _prepare_shared_methods_directory(methods_dir)
                    if dependency_mutation:
                        _prepare_shared_dependencies_directory(dependencies_dir)

        payload, status = _execute_idempotently(workdir, "javascript", request_id, fingerprint, operation)
        return jsonify(payload), status

    @app.post("/python")
    def python():
        parsed = _request_data("code")
        if parsed[0] is None:
            _, error, status = parsed
            return jsonify(error), status
        data, workdir, request_id, timeout = parsed
        code = data["code"]
        fingerprint = hashlib.sha256(
            json.dumps({"code": code, "timeout": timeout}, sort_keys=True).encode("utf-8")
        ).hexdigest()
        session_id = data.get("session_id", "default")
        os.makedirs(workdir, exist_ok=True)
        try:
            isolation = _prepare_session_isolation(session_id, workdir)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            logger.error("Session isolation failed", extra={"session_id": session_id, "error": str(exc)})
            return jsonify({"error": str(exc), "request_id": request_id}), 503
        logger.info("Executing python", extra={"session_id": session_id, "code": code[:200], "timeout": timeout})

        # Execute Python code in a subprocess so that memory-hungry code
        # (e.g. PyTorch model loading) cannot OOM-kill the Flask server.
        # This mirrors how /javascript and /bash already spawn child processes.
        # Use uuid4 to guarantee uniqueness even under concurrent requests.
        def operation() -> tuple[dict, int]:
            py_file = os.path.join(
                isolation["env"]["TMPDIR"],
                f"script-{uuid.uuid4().hex}.py",
            )
            dependency_mutation = _may_modify_dependencies(code)
            lock = dependency_lock if dependency_mutation else nullcontext()
            with lock:
                try:
                    _write_session_script(py_file, code, isolation)
                    stdout, stderr, returncode, failure = _run_bounded(
                        [sys.executable, py_file],
                        workdir=workdir,
                        timeout=timeout,
                        isolation=isolation,
                    )
                    if failure:
                        return {"error": f"Python {failure.lower()}", "request_id": request_id}, 200
                    return {
                        "stdout": stdout,
                        "stderr": stderr,
                        "returncode": returncode,
                        "request_id": request_id,
                    }, 200
                except Exception as exc:
                    logger.error("Python execution failed", exc_info=True)
                    return {"error": str(exc), "request_id": request_id}, 500
                finally:
                    _safe_remove(py_file)
                    _prepare_shared_methods_directory(methods_dir)
                    if dependency_mutation:
                        _prepare_shared_dependencies_directory(dependencies_dir)

        payload, status = _execute_idempotently(workdir, "python", request_id, fingerprint, operation)
        return jsonify(payload), status

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5001"))
    app = create_executor_app()
    app.run(host=os.getenv("EXECUTOR_BIND_HOST", "127.0.0.1"), port=port, debug=False)
