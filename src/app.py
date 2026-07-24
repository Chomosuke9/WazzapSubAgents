"""HTTP API for reliable parent-agent/subagent communication."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import traceback
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from src.agent import ExecutorAgent
from src.concurrency import SubAgentQueue, get_global_queue
from src.config import config
from src.container_client import ContainerClient
from src.docker_manager import DockerManager
from src.input_staging import rehydrate_staged_inputs, stage_request_inputs
from src.logger import get_logger
from src.session_manager import (
    SessionManager,
    SessionPersistenceError,
    validate_session_id,
)
from src.upload_store import UploadError, UploadStore

logger = get_logger(__name__)

_MAX_REQUEST_BYTES = int(
    os.getenv("SUBAGENT_MAX_REQUEST_BYTES", str(300 * 1024 * 1024))
)
_MAX_INSTRUCTION_CHARS = int(os.getenv("SUBAGENT_MAX_INSTRUCTION_CHARS", "100000"))
_API_TOKEN = os.getenv("SUBAGENT_API_TOKEN", "")
_REQUIRE_API_AUTH = os.getenv("SUBAGENT_REQUIRE_API_AUTH", "1").strip().lower()


def _json_body() -> dict[str, Any]:
    if not request.is_json:
        raise BadRequest("Content-Type must be application/json")
    value = request.get_json(silent=False)
    if not isinstance(value, dict):
        raise BadRequest("JSON body must be an object")
    return value


def _instruction(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("instruction must be a non-empty string")
    if len(value) > _MAX_INSTRUCTION_CHARS:
        raise ValueError(f"instruction exceeds {_MAX_INSTRUCTION_CHARS} characters")
    return value


def _optional_url(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError(f"{field} must be an HTTP(S) URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{field} must be an HTTP(S) URL without userinfo")
    return value


def _quality(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    raise ValueError("high_quality must be a boolean")


def _request_fingerprint(data: dict[str, Any], *, steering: bool = False) -> str:
    """Hash the semantic request without materializing another huge JSON body."""
    digest = hashlib.sha256()
    keys = ["session_id", "instruction"]
    if steering:
        keys.append("steering_id")
    else:
        keys.extend(["high_quality", "previous_session_id", "callback_url", "progress_webhook"])
    for key in keys:
        digest.update(key.encode())
        digest.update(json.dumps(data.get(key), ensure_ascii=False, sort_keys=True).encode())
    raw_paths = data.get("input_files") or []
    if isinstance(raw_paths, list):
        for item in raw_paths:
            digest.update(b"path:")
            digest.update(json.dumps(item, ensure_ascii=False, sort_keys=True).encode())
    inline = data.get("input_files_content") or []
    if isinstance(inline, list):
        for item in inline:
            digest.update(b"inline:")
            if not isinstance(item, dict):
                digest.update(repr(item).encode())
                continue
            digest.update(str(item.get("name")).encode())
            digest.update(str(item.get("size")).encode())
            digest.update(str(item.get("sha256")).encode())
            content = item.get("content_base64")
            if isinstance(content, str):
                digest.update(hashlib.sha256(content.encode("ascii", "ignore")).digest())
            else:
                digest.update(repr(content).encode())
    return digest.hexdigest()


def _staging_roots(session_manager: SessionManager) -> tuple[str, str]:
    workdir_base = os.path.realpath(os.getenv("WORKDIR_BASE", session_manager._workdir_base))
    source_root = os.path.realpath(
        os.getenv("SUBAGENT_INPUT_SOURCE_ROOT")
        or os.getenv("SUBAGENT_STORAGE_DIR")
        or os.path.dirname(workdir_base)
    )
    return source_root, workdir_base


def _remove_attempt_files(manifest: dict[str, Any]) -> None:
    for item in manifest.get("staged_files", []):
        path = item.get("path") if isinstance(item, dict) else None
        if isinstance(path, str):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Could not roll back staged file", extra={"path": path})


def _api_auth_error(*, require_configured: bool = False):
    if not _API_TOKEN:
        remote = request.remote_addr or ""
        loopback = remote in {"127.0.0.1", "::1", "localhost"}
        require_auth = os.getenv(
            "SUBAGENT_REQUIRE_API_AUTH", _REQUIRE_API_AUTH
        ).strip().lower() not in {"0", "false", "no", "off"}
        bind_host = os.getenv("SUBAGENT_BIND_HOST", "127.0.0.1").strip()
        loopback_bind = bind_host in {"127.0.0.1", "::1", "localhost"}
        if not require_configured and loopback and loopback_bind and not require_auth:
            return None
        return jsonify({
            "success": False,
            "report": "Secure API is disabled until SUBAGENT_API_TOKEN is configured",
        }), 503
    authorization = request.headers.get("Authorization", "")
    expected = f"Bearer {_API_TOKEN}"
    if not hmac.compare_digest(authorization, expected):
        return jsonify({"success": False, "report": "Unauthorized API request"}), 401
    return None


def _resolve_upload_inputs(
    upload_store: UploadStore,
    raw_inputs: list[Any],
    session_id: str,
) -> tuple[list[Any], list[dict[str, Any]]]:
    resolved: list[Any] = []
    errors: list[dict[str, Any]] = []
    for item in raw_inputs:
        if isinstance(item, dict) and item.get("upload_id") is not None:
            try:
                claimed = upload_store.claim(str(item.get("upload_id")), session_id)
                # The upload's verified identity is authoritative. Optional
                # declarations on /execute must match it rather than replace it.
                requested_name = item.get("name") or item.get("filename")
                if requested_name is not None and requested_name != claimed["name"]:
                    raise UploadError("uploaded filename differs from execute manifest")
                if item.get("size") is not None and item.get("size") != claimed["size"]:
                    raise UploadError("uploaded size differs from execute manifest")
                if item.get("sha256") is not None and str(item.get("sha256")).lower() != claimed["sha256"]:
                    raise UploadError("uploaded sha256 differs from execute manifest")
                resolved.append(claimed)
            except UploadError as exc:
                errors.append({
                    "name": str(item.get("name") or item.get("filename") or "*"),
                    "path": None,
                    "code": exc.code,
                    "error": str(exc),
                })
        else:
            resolved.append(item)
    return resolved, errors


def _upload_ids(raw_inputs: list[Any]) -> list[str]:
    return [
        str(item["upload_id"])
        for item in raw_inputs
        if isinstance(item, dict) and isinstance(item.get("upload_id"), str)
    ]


def create_app(
    docker_mgr: DockerManager | None = None,
    queue: SubAgentQueue | None = None,
    session_manager: SessionManager | None = None,
    container_url: str | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = _MAX_REQUEST_BYTES

    resolved_container_url = container_url or config["container_executor_url"]
    container_client = ContainerClient(resolved_container_url, docker_mgr=docker_mgr)
    if session_manager is None:
        session_manager = SessionManager(idle_timeout=config["session_idle_timeout"])
    subagent_queue = queue if queue is not None else get_global_queue()
    source_root, forbidden_source_root = _staging_roots(session_manager)
    upload_store = UploadStore(
        os.getenv("SUBAGENT_UPLOAD_DIR", os.path.join(source_root, ".subagent_uploads"))
    )

    @app.get("/health")
    def health():
        ready = container_client.health_check()
        body = {
            "status": "ok" if ready else "degraded",
            "executor_ready": ready,
            "executor_url": resolved_container_url,
        }
        return jsonify(body), 200 if ready else 503

    @app.post("/execute")
    def execute():
        auth_error = _api_auth_error()
        if auth_error:
            return auth_error
        try:
            data = _json_body()
            if not data.get("session_id") or not data.get("instruction"):
                raise ValueError("Missing session_id or instruction")
            session_id = validate_session_id(data.get("session_id"))
            instruction = _instruction(data.get("instruction"))
            high_quality = _quality(data.get("high_quality", False))
            callback_url = _optional_url(data.get("callback_url"), "callback_url")
            progress_webhook = _optional_url(data.get("progress_webhook"), "progress_webhook")
            previous_session_id = data.get("previous_session_id")
            if previous_session_id is not None:
                previous_session_id = validate_session_id(previous_session_id)
                if previous_session_id == session_id:
                    raise ValueError("previous_session_id must differ from session_id")
            if data.get("input_files", []) is not None and not isinstance(data.get("input_files", []), list):
                raise ValueError("input_files must be an array")
            if data.get("input_files_content", []) is not None and not isinstance(data.get("input_files_content", []), list):
                raise ValueError("input_files_content must be an array")
        except (ValueError, BadRequest) as exc:
            return jsonify({"accepted": False, "success": False, "report": str(exc)}), 400

        fingerprint = _request_fingerprint(data)
        try:
            session, begin_state = session_manager.begin_execution(session_id, fingerprint)
        except SessionPersistenceError as exc:
            return jsonify({
                "accepted": False,
                "success": False,
                "session_id": session_id,
                "report": str(exc),
            }), 503
        if begin_state == "conflict":
            return jsonify({
                "accepted": False,
                "success": False,
                "session_id": session_id,
                "report": "session_id is already bound to a different execute request",
            }), 409
        if begin_state == "replay":
            # The original request may still be finishing its atomic staging.
            stored = session.request_manifest
            manifest = stored.get("public_manifest", stored) if stored else {}
            if session.status == "completed":
                status_code = 200
            else:
                status_code = 202
            return jsonify({
                "accepted": True,
                "status": "completed" if session.status == "completed" else "processing",
                "session_id": session_id,
                "request_fingerprint": fingerprint,
                "idempotent_replay": True,
                **(manifest or {
                    "requested_file_count": 0,
                    "staged_file_count": 0,
                    "staged_files": [],
                    "file_errors": [],
                }),
            }), status_code

        raw_inputs = data.get("input_files") or []
        raw_inputs, upload_errors = _resolve_upload_inputs(upload_store, raw_inputs, session_id)
        if upload_errors:
            session_manager.cleanup_session(session_id)
            return jsonify({
                "accepted": False,
                "success": False,
                "session_id": session_id,
                "request_fingerprint": fingerprint,
                "report": "One or more uploaded inputs are unavailable or mismatched",
                "requested_file_count": len(data.get("input_files") or []),
                "staged_file_count": 0,
                "staged_files": [],
                "file_errors": upload_errors,
            }), 422
        staging = stage_request_inputs(
            session.workdir,
            raw_inputs,
            data.get("input_files_content") or [],
            source_root=source_root,
            forbidden_source_root=forbidden_source_root,
        )
        public_manifest = staging.as_dict()
        if not staging.complete:
            _remove_attempt_files(public_manifest)
            session_manager.cleanup_session(session_id)
            return jsonify({
                "accepted": False,
                "success": False,
                "session_id": session_id,
                "request_fingerprint": fingerprint,
                "report": "One or more requested input files could not be staged",
                **public_manifest,
            }), 422

        rehydrated_manifest: dict[str, Any] = {
            "requested_file_count": 0,
            "staged_file_count": 0,
            "staged_files": [],
            "file_errors": [],
        }
        rehydrated_paths: list[str] = []
        if previous_session_id is not None:
            previous = session_manager.get_session(previous_session_id)
            if previous is None or previous.status != "completed" or previous.messages is None:
                _remove_attempt_files(public_manifest)
                session_manager.cleanup_session(session_id)
                return jsonify({
                    "accepted": False,
                    "success": False,
                    "session_id": session_id,
                    "report": "previous_session_id is unavailable or has no restorable conversation",
                }), 409
            previous_inputs = rehydrate_staged_inputs(
                session.workdir,
                previous.workdir,
                previous.request_manifest,
            )
            rehydrated_manifest = previous_inputs.as_dict()
            if not previous_inputs.complete:
                _remove_attempt_files(public_manifest)
                _remove_attempt_files(rehydrated_manifest)
                session_manager.cleanup_session(session_id)
                return jsonify({
                    "accepted": False,
                    "success": False,
                    "session_id": session_id,
                    "report": "previous-session input files are no longer available",
                    "previous_session_id": previous_session_id,
                    "rehydration": rehydrated_manifest,
                }), 409
            rehydrated_paths = previous_inputs.paths

        stored_manifest = {
            **public_manifest,
            "staged_files": public_manifest["staged_files"] + rehydrated_manifest["staged_files"],
            "rehydrated_files": rehydrated_manifest["staged_files"],
            "public_manifest": public_manifest,
        }
        session_manager.set_request_manifest(session_id, stored_manifest)
        session_manager.set_callback(session_id, callback_url, progress_webhook)
        upload_store.release(_upload_ids(data.get("input_files") or []), session_id)

        def _emit_queued(sid: str, position: int, queue_size: int) -> None:
            session_manager.fire_queue_event(
                sid,
                {"type": "queued", "session_id": sid, "position": position, "queue_size": queue_size},
            )

        def _emit_advance(updates: list[tuple[str, int, int]]) -> None:
            for sid, position, queue_size in updates:
                session_manager.fire_queue_event(
                    sid,
                    {"type": "queue_advanced", "session_id": sid, "position": position, "queue_size": queue_size},
                )

        def run_agent() -> None:
            acquired = False
            try:
                subagent_queue.acquire(session_id, on_enqueue=_emit_queued, on_advance=_emit_advance)
                acquired = True
                agent = ExecutorAgent(container_client, session_manager)
                result = agent.execute(
                    session_id=session_id,
                    instruction=instruction,
                    input_files=staging.paths + rehydrated_paths,
                    workdir=session.workdir,
                    high_quality=high_quality,
                    previous_session_id=previous_session_id,
                )
                session_manager.store_result(session_id, result)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "Agent execution failed",
                    extra={
                        "session_id": session_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "traceback": "".join(traceback.format_tb(exc.__traceback__)),
                    },
                )
                session_manager.store_result(
                    session_id,
                    {
                        "session_id": session_id,
                        "success": False,
                        "report": f"Agent failed: {exc}",
                        "output_files": [],
                        "processing_time_sec": 0,
                    },
                )
            finally:
                if acquired:
                    subagent_queue.release()

        if not session_manager.mark_execution_started(session_id):
            return jsonify({
                "accepted": True,
                "status": "processing",
                "session_id": session_id,
                "request_fingerprint": fingerprint,
                "idempotent_replay": True,
                **public_manifest,
            }), 202
        threading.Thread(target=run_agent, daemon=True).start()
        return jsonify({
            "accepted": True,
            "success": True,
            "status": "processing",
            "session_id": session_id,
            "request_fingerprint": fingerprint,
            "idempotent_replay": False,
            **public_manifest,
            "rehydrated_files": rehydrated_manifest["staged_files"],
        }), 202

    @app.post("/steer")
    def steer():
        auth_error = _api_auth_error()
        if auth_error:
            return auth_error
        try:
            data = _json_body()
            session_id = validate_session_id(data.get("session_id"))
            instruction = _instruction(data.get("instruction"))
            steering_id = data.get("steering_id")
            if steering_id is None:
                steering_id = f"steer-{hashlib.sha256(os.urandom(32)).hexdigest()[:24]}"
                data["steering_id"] = steering_id
            steering_id = validate_session_id(steering_id)
            if not isinstance(data.get("input_files", []), list):
                raise ValueError("input_files must be an array")
            if not isinstance(data.get("input_files_content", []), list):
                raise ValueError("input_files_content must be an array")
        except (ValueError, BadRequest) as exc:
            return jsonify({"accepted": False, "success": False, "report": str(exc)}), 400

        session = session_manager.get_session(session_id)
        if session is None or session.status != "active":
            return jsonify({
                "accepted": False,
                "success": False,
                "session_id": session_id,
                "report": "Session not found or not active",
            }), 404

        fingerprint = _request_fingerprint(data, steering=True)
        existing = session_manager.lookup_steering(session_id, steering_id)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                return jsonify({
                    "accepted": False,
                    "success": False,
                    "session_id": session_id,
                    "steering_id": steering_id,
                    "report": "steering_id is already bound to a different request",
                }), 409
            return jsonify({
                "accepted": True,
                "success": True,
                "session_id": session_id,
                "steering_id": steering_id,
                "state": existing.state,
                "idempotent_replay": True,
                **existing.manifest,
            }), 202

        raw_inputs = data.get("input_files") or []
        raw_inputs, upload_errors = _resolve_upload_inputs(upload_store, raw_inputs, session_id)
        if upload_errors:
            return jsonify({
                "accepted": False,
                "success": False,
                "session_id": session_id,
                "steering_id": steering_id,
                "report": "One or more uploaded steering inputs are unavailable or mismatched",
                "requested_file_count": len(data.get("input_files") or []),
                "staged_file_count": 0,
                "staged_files": [],
                "file_errors": upload_errors,
            }), 422
        staging = stage_request_inputs(
            session.workdir,
            raw_inputs,
            data.get("input_files_content") or [],
            source_root=source_root,
            forbidden_source_root=forbidden_source_root,
        )
        manifest = staging.as_dict()
        if not staging.complete:
            _remove_attempt_files(manifest)
            return jsonify({
                "accepted": False,
                "success": False,
                "session_id": session_id,
                "steering_id": steering_id,
                "report": "One or more steered files could not be staged",
                **manifest,
            }), 422

        steer_message = instruction
        if staging.paths:
            files_block = "\n".join(f"- {path}" for path in staging.paths)
            steer_message = (
                f"{instruction}\n\n"
                "[NEW INPUT FILES - provided with this steering instruction, "
                f"read them from these paths]:\n{files_block}"
            )
        envelope, queue_state = session_manager.queue_steering(
            session_id,
            steering_id,
            steer_message,
            fingerprint,
            manifest,
        )
        if queue_state == "conflict":
            _remove_attempt_files(manifest)
            return jsonify({"accepted": False, "success": False, "report": "steering_id conflict"}), 409
        if envelope is None:
            _remove_attempt_files(manifest)
            return jsonify({"accepted": False, "success": False, "report": "Session no longer active"}), 409
        if queue_state == "replay":
            _remove_attempt_files(manifest)
            manifest = envelope.manifest
        else:
            # The steering envelope and its file manifest are now durable, so
            # the temporary upload can be released without harming retries.
            upload_store.release(_upload_ids(data.get("input_files") or []), session_id)
        return jsonify({
            "accepted": True,
            "success": True,
            "session_id": session_id,
            "steering_id": steering_id,
            "state": envelope.state,
            "idempotent_replay": queue_state == "replay",
            **manifest,
        }), 202

    @app.get("/sessions/<session_id>/steering/<steering_id>")
    def steering_status(session_id: str, steering_id: str):
        auth_error = _api_auth_error()
        if auth_error:
            return auth_error
        try:
            validate_session_id(session_id)
            validate_session_id(steering_id)
        except ValueError as exc:
            return jsonify({"success": False, "report": str(exc)}), 400
        status = session_manager.get_steering_status(session_id, steering_id)
        if status is None:
            return jsonify({"success": False, "report": "Steering acknowledgement not found"}), 404
        return jsonify(status), 200

    @app.get("/sessions/<session_id>/result")
    def get_result(session_id: str):
        auth_error = _api_auth_error()
        if auth_error:
            return auth_error
        try:
            validate_session_id(session_id)
        except ValueError as exc:
            return jsonify({"success": False, "report": str(exc)}), 400
        session = session_manager.get_session(session_id)
        if session is None:
            return jsonify({"success": False, "report": "Session not found or expired"}), 404
        result = session_manager.get_result(session_id, delivery=True)
        if result is None:
            return jsonify({"success": True, "status": "processing", "session_id": session_id}), 202
        return jsonify(result), 200

    @app.get("/sessions/<session_id>/outputs/<file_id>")
    def download_output(session_id: str, file_id: str):
        auth_error = _api_auth_error(require_configured=True)
        if auth_error:
            return auth_error
        try:
            validate_session_id(session_id)
            if len(file_id) != 40 or any(char not in "0123456789abcdef" for char in file_id):
                raise ValueError("Invalid output file_id")
        except ValueError as exc:
            return jsonify({"success": False, "report": str(exc)}), 400
        opened = session_manager.open_output_file(session_id, file_id)
        if opened is None:
            return jsonify({"success": False, "report": "Output file not found or no longer valid"}), 404
        handle, metadata = opened
        response = send_file(
            handle,
            mimetype=metadata["mime"],
            as_attachment=True,
            download_name=metadata["name"],
            conditional=False,
            max_age=0,
        )
        response.content_length = metadata["size_bytes"]
        response.headers["X-Content-SHA256"] = metadata["sha256"]
        response.headers["X-Output-File-Id"] = metadata["file_id"]
        response.headers["Cache-Control"] = "no-store"
        response.call_on_close(handle.close)
        return response

    @app.post("/uploads/init")
    def initiate_upload():
        auth_error = _api_auth_error(require_configured=True)
        if auth_error:
            return auth_error
        try:
            data = _json_body()
            metadata, replay = upload_store.initiate(
                upload_id=data.get("upload_id"),
                filename=data.get("filename"),
                size=data.get("size"),
                sha256=data.get("sha256"),
            )
            return jsonify({
                "success": True,
                "upload_id": metadata["upload_id"],
                "filename": metadata["filename"],
                "size": metadata["size"],
                "sha256": metadata["sha256"],
                "state": metadata["state"],
                "max_chunk_bytes": upload_store.max_chunk_bytes,
                "idempotent_replay": replay,
            }), 200 if replay else 201
        except (UploadError, BadRequest) as exc:
            status = exc.status if isinstance(exc, UploadError) else 400
            code = exc.code if isinstance(exc, UploadError) else "invalid_request"
            return jsonify({"success": False, "code": code, "report": str(exc)}), status

    @app.put("/uploads/<upload_id>/chunks/<int:index>")
    def upload_chunk(upload_id: str, index: int):
        auth_error = _api_auth_error(require_configured=True)
        if auth_error:
            return auth_error
        try:
            content_length = request.content_length
            if content_length is not None and content_length > upload_store.max_chunk_bytes:
                raise UploadError("chunk exceeds configured size limit", code="chunk_too_large", status=413)
            data = request.stream.read(upload_store.max_chunk_bytes + 1)
            if len(data) > upload_store.max_chunk_bytes:
                raise UploadError("chunk exceeds configured size limit", code="chunk_too_large", status=413)
            descriptor, replay = upload_store.put_chunk(
                upload_id,
                index,
                request.headers.get("Content-Range"),
                data,
            )
            return jsonify({
                "success": True,
                "upload_id": upload_id,
                "chunk": descriptor,
                "idempotent_replay": replay,
            }), 200 if replay else 201
        except UploadError as exc:
            return jsonify({"success": False, "code": exc.code, "report": str(exc)}), exc.status

    @app.post("/uploads/<upload_id>/complete")
    def complete_upload(upload_id: str):
        auth_error = _api_auth_error(require_configured=True)
        if auth_error:
            return auth_error
        try:
            metadata, replay = upload_store.complete(upload_id)
            return jsonify({
                "success": True,
                "upload_id": upload_id,
                "filename": metadata["filename"],
                "size": metadata["size"],
                "sha256": metadata["sha256"],
                "complete": True,
                "state": "complete",
                "idempotent_replay": replay,
            }), 200
        except UploadError as exc:
            return jsonify({"success": False, "code": exc.code, "report": str(exc)}), exc.status

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return jsonify({"accepted": False, "success": False, "report": "Request body exceeds configured limit"}), 413

    @app.errorhandler(BadRequest)
    def bad_request(error):
        return jsonify({"accepted": False, "success": False, "report": str(error)}), 400

    @app.errorhandler(SessionPersistenceError)
    def persistence_unavailable(error):
        return jsonify({
            "accepted": False,
            "success": False,
            "report": str(error),
        }), 503

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Unhandled API error", exc_info=error)
        return jsonify({"accepted": False, "success": False, "report": "Internal server error"}), 500

    return app
