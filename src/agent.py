import json
import os
import time
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import messages_to_dict, messages_from_dict

from src.config import config
from src.container_client import ContainerClient
from src.logger import get_logger
from src.session_manager import SessionManager
from src.prompts import EXECUTOR_SYSTEM_PROMPT
from src.secrets_redaction import redact_secrets

logger = get_logger(__name__)


# Resilience tunables (overridable via env)
LLM_RETRY_MAX = int(os.getenv("AGENT_LLM_RETRY_MAX", "5"))
LLM_RETRY_BASE_BACKOFF = float(os.getenv("AGENT_LLM_RETRY_BASE_BACKOFF", "2.0"))
LLM_RETRY_MAX_BACKOFF = float(os.getenv("AGENT_LLM_RETRY_MAX_BACKOFF", "60.0"))
STUCK_LOOP_THRESHOLD = int(os.getenv("AGENT_STUCK_LOOP_THRESHOLD", "5"))
# How many times to re-invoke the LLM at the same turn when it returns plain
# text (no native tool_call). Prevents infinite loops on a misconfigured model.
NO_TOOL_RETRY_MAX = int(os.getenv("AGENT_NO_TOOL_RETRY_MAX", "3"))


# Tool schemas — passed to ``ChatOpenAI.bind_tools`` so the model emits
# native ``tool_calls`` instead of having to embed JSON in plain text.
# A ``reason`` field is required on every tool so the progress webhook can
# surface *why* the agent ran each step, which is what shows up in the
# bridge's "Active sub-agent task" context block on subsequent LLM2 turns.
BASH_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Execute a bash shell."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short explanation of WHY you are running this command.",
                    "minLength": 1,
                },
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                    "minLength": 1,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum time in seconds to wait for the command to finish. Default is 10.",
                    "default": 10,
                },
            },
            "required": ["reason", "command"],
            "additionalProperties": False,
        },
    },
}

PYTHON_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "python",
        "description": (
            "Execute Python code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short explanation of WHY you are running this code.",
                    "minLength": 1,
                },
                "code": {
                    "type": "string",
                    "description": "The Python source code to execute.",
                    "minLength": 1,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum time in seconds to wait for the code to finish. Default is 10.",
                    "default": 10,
                },
            },
            "required": ["reason", "code"],
            "additionalProperties": False,
        },
    },
}

END_TASK_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "end_task",
        "description": (
            "Finish the task and report results back to the caller.\n"
            "Call this when the instruction is fully resolved or cannot be completed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "True if the task was completed successfully.",
                },
                "report": {
                    "type": "string",
                    "description": (
                        "Final report for the caller. Be concise but "
                        "include any information the user will need."
                    ),
                },
                "output_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional. Absolute paths of files to be sent back to the user.\n"
                        "- Include only final deliverables (reports, generated images, etc.).\n"
                        "- Exclude temporary files, logs, or scripts.\n"
                        "- Paths must be within the workdir."
                    ),
                },
            },
            "required": ["success", "report"],
            "additionalProperties": False,
        },
    },
}

JAVASCRIPT_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "javascript",
        "description": (
            "Execute JavaScript code (Node.js 24)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short explanation of WHY you are running this code.",
                    "minLength": 1,
                },
                "code": {
                    "type": "string",
                    "description": "The JavaScript source code to execute.",
                    "minLength": 1,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum time in seconds to wait for the code to finish. Default is 10.",
                    "default": 10,
                },
            },
            "required": ["reason", "code"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    BASH_TOOL_SCHEMA,
    PYTHON_TOOL_SCHEMA,
    JAVASCRIPT_TOOL_SCHEMA,
    END_TASK_TOOL_SCHEMA,
]


def _is_retryable_llm_error(err: BaseException) -> bool:
  """Decide whether an LLM SDK error is worth retrying.

  Retries on rate limits, transient server errors, and connection/timeout
  errors. Anything else (auth, bad request, schema) bubbles up immediately.
  """
  name = type(err).__name__.lower()
  if "ratelimit" in name or "rate_limit" in name:
    return True
  if "timeout" in name or "connect" in name or "apiconnection" in name:
    return True
  status = getattr(err, "status_code", None)
  if status is None:
    response = getattr(err, "response", None)
    if response is not None:
      status = getattr(response, "status_code", None)
  if isinstance(status, int) and (status == 429 or 500 <= status < 600):
    return True
  return False


def _retry_after_seconds(err: BaseException) -> Optional[float]:
  """Honour Retry-After header when the provider sends one."""
  response = getattr(err, "response", None)
  headers = getattr(response, "headers", None) if response is not None else None
  if not headers:
    return None
  try:
    raw = headers.get("Retry-After") or headers.get("retry-after")
  except Exception:
    return None
  if not raw:
    return None
  try:
    return max(0.0, float(raw))
  except (TypeError, ValueError):
    return None


class ExecutorAgent:
    def __init__(self, container_client: ContainerClient, session_manager: SessionManager, logger_override=None):
        self.container_client = container_client
        self.session_manager = session_manager
        self.logger = logger_override or logger
        base_url_kwargs = {"base_url": config["llm_base_url"]} if config["llm_base_url"] else {}
        self.llm_low = ChatOpenAI(
            model=config["agent_model_low"],
            temperature=config["agent_temperature_low"],
            api_key=config["llm_api_key"],
            **base_url_kwargs,
        ).bind_tools(TOOL_SCHEMAS)
        self.llm_high = ChatOpenAI(
            model=config["agent_model_high"],
            temperature=config["agent_temperature_high"],
            api_key=config["llm_api_key"],
            **base_url_kwargs,
        ).bind_tools(TOOL_SCHEMAS)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------
    def _bash_tool(self, reason: str, command: str, session_id: str, timeout: int = 10) -> str:
        self.session_manager.append_progress(session_id, {
            "step": "bash",
            "reason": (reason or "")[:500],
            "detail": str({"reason": reason, "command": command})[:500],
            "timestamp": time.time(),
        })
        result = self.container_client.run_bash(command, session_id=session_id, timeout=timeout)
        self.logger.info(
            "bash_tool executed",
            extra={
                "session_id": session_id,
                "reason": (reason or "")[:200],
                "command": command[:200],
                "returncode": result.get("returncode"),
            },
        )
        if "error" in result:
            return (
                f"ERROR:\n{result['error']}"
                f"\nSTDOUT:\n{result.get('stdout', '')}"
                f"\nSTDERR:\n{result.get('stderr', '')}"
                f"\nRETURNCODE: {result.get('returncode')}"
            )
        output = f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}\nRETURNCODE: {result.get('returncode')}"
        return output

    def _python_tool(self, reason: str, code: str, session_id: str, timeout: int = 10) -> str:
        self.session_manager.append_progress(session_id, {
            "step": "python",
            "reason": (reason or "")[:500],
            "detail": str({"reason": reason, "code": code})[:500],
            "timestamp": time.time(),
        })
        result = self.container_client.run_python(code, session_id=session_id, timeout=timeout)
        self.logger.info(
            "python_tool executed",
            extra={
                "session_id": session_id,
                "reason": (reason or "")[:200],
                "code": code[:200],
                "returncode": result.get("returncode"),
            },
        )
        if "error" in result:
            return (
                f"ERROR:\n{result['error']}"
                f"\nSTDOUT:\n{result.get('stdout', '')}"
                f"\nSTDERR:\n{result.get('stderr', '')}"
                f"\nRETURNCODE: {result.get('returncode')}"
            )
        output = f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}\nRETURNCODE: {result.get('returncode')}"
        return output

    def _javascript_tool(self, reason: str, code: str, session_id: str, timeout: int = 10) -> str:
        self.session_manager.append_progress(session_id, {
            "step": "javascript",
            "reason": (reason or "")[:500],
            "detail": str({"reason": reason, "code": code})[:500],
            "timestamp": time.time(),
        })
        result = self.container_client.run_javascript(code, session_id=session_id, timeout=timeout)
        self.logger.info(
            "javascript_tool executed",
            extra={
                "session_id": session_id,
                "reason": (reason or "")[:200],
                "code": code[:200],
            },
        )
        if "error" in result:
            return (
                f"ERROR:\n{result['error']}"
                f"\nSTDOUT:\n{result.get('stdout', '')}"
                f"\nSTDERR:\n{result.get('stderr', '')}"
                f"\nRETURNCODE: {result.get('returncode')}"
            )
        output = f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}\nRETURNCODE: {result.get('returncode')}"
        return output

    @staticmethod
    def _redact_secrets_in_files(file_paths: List[str], session_id: str) -> None:
        """Scan output files for known secret values and overwrite with
        redacted content. Binary files and very large files are skipped
        silently. Only overwrites when a secret was actually found."""
        # 1 MB cap — skip very large files to avoid memory issues
        MAX_FILE_SIZE = 1 * 1024 * 1024

        for path in file_paths:
            try:
                if os.path.getsize(path) > MAX_FILE_SIZE:
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                # Binary file or unreadable — skip
                continue

            redacted = redact_secrets(content)
            if redacted != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(redacted)
                logger.warning(
                    "Redacted secrets from output file",
                    extra={"session_id": session_id, "file": path},
                )

    def _end_task_tool(
        self,
        success: bool,
        report: str,
        session_id: str,
        output_files: List[str] | None = None,
    ) -> dict:
        self.logger.info(
            "end_task_tool called",
            extra={
                "session_id": session_id,
                "success": success,
                "output_files_count": len(output_files or []),
            },
        )
        return {
            "success": success,
            "report": report,
            "output_files": list(output_files or []),
        }

    def _dispatch_tool(self, tool_name: str, arguments: Dict[str, Any], session_id: str) -> Any:
        """Run the named tool with ``arguments``. Raises ``KeyError`` for
        unknown tools so the caller can decide how to recover."""
        if tool_name == "bash":
            return self._bash_tool(
                reason=arguments.get("reason", ""),
                command=arguments.get("command", ""),
                session_id=session_id,
                timeout=arguments.get("timeout", 10),
            )
        if tool_name == "python":
            return self._python_tool(
                reason=arguments.get("reason", ""),
                code=arguments.get("code", ""),
                session_id=session_id,
                timeout=arguments.get("timeout", 10),
            )
        if tool_name == "javascript":
            return self._javascript_tool(
                reason=arguments.get("reason", ""),
                code=arguments.get("code", ""),
                session_id=session_id,
                timeout=arguments.get("timeout", 10),
            )
        if tool_name == "end_task":
            raw_output_files = arguments.get("output_files")
            if raw_output_files is None:
                normalized_output_files: list[str] = []
            elif isinstance(raw_output_files, list):
                # Drop non-string entries defensively rather than crashing
                # on a malformed tool call — a misbehaving model shouldn't
                # be able to break the whole agent loop.
                normalized_output_files = [
                    str(p) for p in raw_output_files if isinstance(p, str) and p.strip()
                ]
            else:
                self.logger.warning(
                    "end_task: output_files was not a list (got %s); ignoring",
                    type(raw_output_files).__name__,
                    extra={"session_id": session_id},
                )
                normalized_output_files = []
            return self._end_task_tool(
                success=bool(arguments.get("success", False)),
                report=str(arguments.get("report", "") or ""),
                session_id=session_id,
                output_files=normalized_output_files,
            )
        raise KeyError(tool_name)

    # ------------------------------------------------------------------
    # Output collection / prompt construction
    # ------------------------------------------------------------------
    def _resolve_declared_output_files(
        self,
        workdir: str,
        declared: List[str],
        session_id: str,
    ) -> List[str]:
        """Validate the explicit ``output_files`` list passed to ``end_task``.

        Only paths that meet ALL of the following are accepted:

        - resolve to a regular file that exists,
        - sit inside ``workdir`` (no traversal outside the sandbox).

        Anything else is dropped with a logged warning. Returning a strict
        subset (rather than failing the whole task) lets the user still get
        the textual report when the model lists a couple of bogus paths.
        """
        if not declared:
            return []

        try:
            workdir_real = os.path.realpath(workdir)
        except OSError:
            return []

        accepted: list[str] = []
        skipped: list[dict] = []
        seen: set[str] = set()
        for raw_path in declared:
            try:
                resolved = os.path.realpath(raw_path)
            except OSError:
                skipped.append({"path": raw_path, "reason": "realpath_failed"})
                continue

            if not os.path.isfile(resolved):
                skipped.append({"path": raw_path, "reason": "not_a_file"})
                continue

            # Strict containment check — ``startswith`` alone would let
            # ``<workdir>foo`` slip past, so anchor with the path separator.
            if (
                resolved != workdir_real
                and not resolved.startswith(workdir_real + os.sep)
            ):
                skipped.append({"path": raw_path, "reason": "outside_workdir"})
                continue



            if resolved in seen:
                continue
            seen.add(resolved)
            accepted.append(resolved)

        if skipped:
            self.logger.warning(
                "end_task: dropped %d declared output_file(s)",
                len(skipped),
                extra={"session_id": session_id, "skipped": skipped},
            )

        # Scan output files for leaked secrets and redact in-place.
        # The agent could write keys to files (intentionally or not), e.g.
        #   echo $BRAVE_SEARCH_API_KEY > api_key.txt
        # and then list that file as an output_file. We strip known secret
        # values from text files before they reach the user.
        self._redact_secrets_in_files(accepted, session_id=session_id)

        return accepted

    def _build_system_prompt(self, workdir: str) -> str:
        return EXECUTOR_SYSTEM_PROMPT.format(workdir=workdir)

    # ------------------------------------------------------------------
    # Tool-call extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _patch_dangling_tool_calls(messages: List[Any]) -> None:
        """Append synthetic ToolMessages for any AIMessage tool_calls that
        lack a corresponding ToolMessage response.

        The OpenAI API requires that every tool_call in an AIMessage has a
        matching ToolMessage with the same tool_call_id.  When the agent
        loop exits early (end_task, stuck-loop detector, LLM error), an
        AIMessage may include tool_calls that never received ToolMessage
        responses.  Calling this before storing/restoring the history prevents a
        400 error on re-invoke with ``previous_session_id``.

        This method processes ALL AIMessages (not just the last one) because
        restored conversation history may contain earlier AIMessages with
        unanswered tool_calls that were not patched in a prior run.
        """
        if not messages:
            return

        answered_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, ToolMessage) and getattr(msg, "tool_call_id", None):
                answered_ids.add(msg.tool_call_id)

        for msg in messages:
            if not isinstance(msg, AIMessage):
                continue
            tool_calls = getattr(msg, "tool_calls", None) or []
            unanswered = [
                tc for tc in tool_calls
                if (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None))
                not in answered_ids
            ]
            for tc in unanswered:
                if isinstance(tc, dict):
                    tc_id = tc.get("id", "")
                    tc_name = tc.get("name", "")
                else:
                    tc_id = getattr(tc, "id", "")
                    tc_name = getattr(tc, "name", "")
                synthetic = ToolMessage(
                    content="[Task ended — this tool call was not executed because the agent finished its run.]",
                    tool_call_id=tc_id,
                    name=tc_name,
                )
                messages.append(synthetic)
                answered_ids.add(tc_id)

    @staticmethod
    def _sanitize_messages(messages: List[Any]) -> List[Any]:
        """Remove orphaned ToolMessages and ensure every ToolMessage follows
        an AIMessage with a matching tool_call_id.

        The OpenAI API rejects request payloads where a ``tool`` role message
        does not immediately follow an ``assistant`` message that includes the
        corresponding ``tool_calls`` entry.  This can happen when conversation
        history is restored from a previous session (via
        ``previous_session_id``) and the serialisation/deserialisation round-
        trip loses the ``tool_calls`` attribute on an AIMessage, or when an
        earlier version of ``_patch_dangling_tool_calls`` only patched the
        tail rather than every AIMessage.

        This method returns a *new* list with orphaned ToolMessages removed
        and dangling tool_calls patched (via ``_patch_dangling_tool_calls``).
        """
        if not messages:
            return list(messages)

        sanitized: List[Any] = []
        ai_tool_call_ids: set[str] = set()

        for msg in messages:
            if isinstance(msg, AIMessage):
                ai_tool_call_ids = set()
                tool_calls = getattr(msg, "tool_calls", None) or []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id")
                    else:
                        tc_id = getattr(tc, "id", None)
                    if tc_id:
                        ai_tool_call_ids.add(tc_id)
                sanitized.append(msg)
            elif isinstance(msg, ToolMessage):
                tc_id = getattr(msg, "tool_call_id", None)
                if tc_id and tc_id in ai_tool_call_ids:
                    sanitized.append(msg)
                else:
                    logger.warning(
                        "Dropping orphaned ToolMessage (tool_call_id=%s)",
                        tc_id,
                        extra={"tool_call_id": tc_id},
                    )
            else:
                ai_tool_call_ids = set()
                sanitized.append(msg)

        ExecutorAgent._patch_dangling_tool_calls(sanitized)
        return sanitized

    @staticmethod
    def _normalize_tool_calls(response: Any) -> List[Dict[str, Any]]:
        """Return a list of ``{name, args, id}`` dicts from a LangChain
        response, normalising across both the dict and object forms used
        by different LangChain versions."""
        raw = getattr(response, "tool_calls", None)
        if not isinstance(raw, list) or not raw:
            return []
        normalised: List[Dict[str, Any]] = []
        for tc in raw:
            name: Optional[str] = None
            args: Any = None
            tc_id: Optional[str] = None
            if isinstance(tc, dict):
                name = tc.get("name") or (tc.get("function") or {}).get("name")
                args = tc.get("args")
                if args is None:
                    raw_args = (tc.get("function") or {}).get("arguments")
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}
                    elif isinstance(raw_args, dict):
                        args = raw_args
                tc_id = tc.get("id") or tc.get("tool_call_id")
            else:
                name = getattr(tc, "name", None)
                args = getattr(tc, "args", None)
                tc_id = getattr(tc, "id", None) or getattr(tc, "tool_call_id", None)
            if not name:
                continue
            if not isinstance(args, dict):
                args = {}
            if not tc_id:
                # Some providers do not echo an id for every call; synthesise
                # one so we can still build a matching ``ToolMessage``.
                tc_id = f"call_{len(normalised)}_{int(time.time() * 1000)}"
            normalised.append({"name": name, "args": args, "id": tc_id})
        return normalised

    # ------------------------------------------------------------------
    # LLM invocation with retry on transient errors
    # ------------------------------------------------------------------
    def _invoke_llm_with_retry(self, messages: List[Any], session_id: str, llm: Any = None) -> Any:
        """Call the LLM with bounded retries for transient errors.

        A single transient failure (rate limit, network blip, 5xx) used to
        kill the entire sub-task. We now retry up to ``LLM_RETRY_MAX`` times
        with exponential backoff, honouring ``Retry-After`` when given.
        """
        active_llm = llm if llm is not None else self.llm_low
        attempts = max(1, LLM_RETRY_MAX + 1)
        last_err: Optional[BaseException] = None
        for attempt in range(1, attempts + 1):
            try:
                return active_llm.invoke(messages)
            except Exception as err:  # pylint: disable=broad-except
                last_err = err
                retryable = _is_retryable_llm_error(err)
                if not retryable or attempt >= attempts:
                    self.logger.error(
                        "LLM invoke failed permanently",
                        extra={
                            "session_id": session_id,
                            "attempt": attempt,
                            "attempts": attempts,
                            "error": str(err),
                            "error_type": type(err).__name__,
                            "retryable": retryable,
                        },
                    )
                    raise
                backoff = _retry_after_seconds(err)
                if backoff is None:
                    backoff = min(
                        LLM_RETRY_MAX_BACKOFF,
                        LLM_RETRY_BASE_BACKOFF * (2 ** (attempt - 1)),
                    )
                self.logger.warning(
                    "LLM invoke transient error; retrying",
                    extra={
                        "session_id": session_id,
                        "attempt": attempt,
                        "attempts": attempts,
                        "backoff_s": backoff,
                        "error": str(err),
                        "error_type": type(err).__name__,
                    },
                )
                time.sleep(backoff)
        # Defensive — loop above should always either return or raise.
        if last_err is not None:
            raise last_err
        raise RuntimeError("LLM invoke loop terminated without a result")

    def _invoke_until_tool_call(
        self,
        messages: List[Any],
        session_id: str,
        iteration: int,
        llm: Any = None,
    ) -> tuple[Any, List[Dict[str, Any]]]:
        """Invoke the LLM, retrying *at the same turn* when the response
        contains no native ``tool_calls``.

        We deliberately do NOT append the bad ``AIMessage`` to ``messages``
        between retries — the goal is to give the model a fresh attempt
        from the exact same point rather than letting it see (and double
        down on) its own earlier non-tool reply.
        """
        attempts = max(1, NO_TOOL_RETRY_MAX + 1)
        last_response: Any = None
        for attempt in range(1, attempts + 1):
            response = self._invoke_llm_with_retry(messages, session_id=session_id, llm=llm)
            tool_calls = self._normalize_tool_calls(response)
            last_response = response
            if tool_calls:
                if attempt > 1:
                    self.logger.info(
                        "LLM produced a tool_call after no-tool retry",
                        extra={
                            "session_id": session_id,
                            "iteration": iteration,
                            "attempt": attempt,
                        },
                    )
                return response, tool_calls
            content = response.content
            if isinstance(content, list):
                content = "\n".join(str(c) for c in content)
            self.logger.warning(
                "LLM returned no tool_call; retrying same turn",
                extra={
                    "session_id": session_id,
                    "iteration": iteration,
                    "attempt": attempt,
                    "attempts": attempts,
                    "content_preview": str(content)[:300],
                },
            )
        return last_response, []

    # ------------------------------------------------------------------
    # Message serialization helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _serialize_messages(messages: List[Any]) -> List[Dict[str, Any]]:
        return messages_to_dict(messages)

    @staticmethod
    def _deserialize_messages(data: List[Dict[str, Any]]) -> List[Any]:
        if not data:
            return []
        try:
            return messages_from_dict(data)
        except Exception:
            # Fallback: handle the legacy serialisation format (flat dicts
            # with "role" key) that was used before switching to
            # LangChain's built-in serialisation.  Old stored sessions may
            # contain this format, so we must be able to read them back.
            messages: List[Any] = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                # If the entry uses LangChain's new format (has "type" key
                # at the top level), skip it — messages_from_dict already
                # handled it above or it wasn't the reason we fell back.
                if "type" in entry and "data" in entry:
                    continue
                role = entry.get("role", "")
                content = entry.get("content", "")
                if role == "system":
                    messages.append(SystemMessage(content=content))
                elif role in ("human", "user"):
                    messages.append(HumanMessage(content=content))
                elif role in ("ai", "assistant"):
                    tool_calls = entry.get("tool_calls")
                    if tool_calls:
                        messages.append(AIMessage(content=content, tool_calls=tool_calls))
                    else:
                        messages.append(AIMessage(content=content))
                elif role == "tool":
                    messages.append(ToolMessage(
                        content=content,
                        tool_call_id=entry.get("tool_call_id", ""),
                        name=entry.get("name"),
                    ))
            return messages

    # ------------------------------------------------------------------
    # Main agent loop
    # ------------------------------------------------------------------
    def execute(
        self,
        session_id: str,
        instruction: str,
        input_files: List[str],
        workdir: str,
        high_quality: bool = False,
        previous_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        # Select LLM based on high_quality flag — store as a local to avoid
        # mutating self and risking a data race if the instance is ever reused.
        llm = self.llm_high if high_quality else self.llm_low
        self.logger.info(
            "Agent loop starting",
            extra={
                "session_id": session_id,
                "high_quality": high_quality,
                "previous_session_id": previous_session_id,
            },
        )

        messages: List[Any] = [
            SystemMessage(content=self._build_system_prompt(workdir)),
        ]

        # If this is a correction re-dispatch, carry forward the previous
        # session's conversation history so the agent can continue where it
        # left off instead of starting fresh.
        prev_messages: Optional[List[Dict[str, Any]]] = None
        if previous_session_id is not None:
            prev_messages = self.session_manager.get_messages(previous_session_id)
            if prev_messages is not None:
                # Strip the old system prompt (index 0) — the new session has
                # its own system prompt with updated context. Keep everything
                # from the old conversation: HumanMessages, AIMessages with
                # tool_calls, ToolMessages, etc.
                old_messages = self._deserialize_messages(prev_messages)
                old_conversation = [m for m in old_messages if not isinstance(m, SystemMessage)]
                # Sanitise the restored history to remove orphaned ToolMessages
                # and patch any dangling tool_calls.  The serialisation /
                # deserialisation round-trip can lose tool_calls on AIMessages,
                # leaving ToolMessages that reference non-existent
                # tool_call_ids and trigger a 400 from the API.
                old_conversation = self._sanitize_messages(old_conversation)
                messages.extend(old_conversation)
                self.logger.info(
                    "Restored previous conversation",
                    extra={
                        "session_id": session_id,
                        "previous_session_id": previous_session_id,
                        "restored_count": len(old_conversation),
                    },
                )
            else:
                self.logger.warning(
                    "Previous session messages not found (may have expired)",
                    extra={
                        "session_id": session_id,
                        "previous_session_id": previous_session_id,
                    },
                )

        if input_files:
            files_block = "\n".join(f"- {p}" for p in input_files)
            instruction = (
                f"{instruction}\n\n"
                "[NEW INPUT FILES — provided with this task, "
                "read them from these paths]:\n"
                f"{files_block}"
            )
        messages.append(HumanMessage(content=instruction))

        max_iterations = 50
        final_result: Optional[Dict[str, Any]] = None
        last_signature: Optional[str] = None
        repeat_count = 0

        for i in range(max_iterations):
            try:
                response, tool_calls = self._invoke_until_tool_call(
                    messages,
                    session_id=session_id,
                    iteration=i,
                    llm=llm,
                )
            except Exception as err:  # pylint: disable=broad-except
                final_result = {
                    "success": False,
                    "report": f"LLM invocation failed after retries: {err}",
                }
                break

            content = getattr(response, "content", "")
            if isinstance(content, list):
                content = "\n".join(str(c) for c in content)
            self.logger.info(
                "LLM response",
                extra={
                    "session_id": session_id,
                    "iteration": i,
                    "tool_calls": len(tool_calls),
                    "content_preview": str(content)[:300],
                },
            )

            if not tool_calls:
                # All retries at this turn produced plain text — give up
                # rather than spin in an infinite loop.
                final_result = {
                    "success": False,
                    "report": (
                        "Agent failed to emit a native tool_call after "
                        f"{NO_TOOL_RETRY_MAX} retries at turn {i}."
                    ),
                }
                break

            # Append the AIMessage carrying the tool_calls so the next turn
            # is a valid OpenAI tool-calling history (AIMessage with
            # tool_calls → ToolMessages with matching ids).
            messages.append(response)

            # We process tool calls sequentially; if the model emits more
            # than one in a single turn we still execute them all and feed
            # results back as separate ``ToolMessage`` entries before the
            # next LLM invocation.
            end_task_called = False
            for tc in tool_calls:
                tool_name = tc["name"]
                arguments = tc["args"] or {}
                tc_id = tc["id"]

                if tool_name == "end_task":
                    final_result = self._dispatch_tool(tool_name, arguments, session_id=session_id)
                    end_task_called = True
                    break

                if tool_name not in {"bash", "python", "javascript"}:
                    messages.append(ToolMessage(
                        content=f"Tool '{tool_name}' is not available. Use bash, python, javascript, or end_task.",
                        tool_call_id=tc_id,
                        name=tool_name,
                    ))
                    continue

                # Track repeated identical tool calls so we can break out
                # of obvious loops (same command/code with same reason).
                try:
                    signature = json.dumps(
                        {"tool": tool_name, "arguments": arguments},
                        sort_keys=True,
                        default=str,
                    )
                except Exception:
                    signature = f"{tool_name}:{arguments}"
                if signature == last_signature:
                    repeat_count += 1
                else:
                    repeat_count = 1
                    last_signature = signature
                if STUCK_LOOP_THRESHOLD > 0 and repeat_count >= STUCK_LOOP_THRESHOLD:
                    self.logger.warning(
                        "Agent appears stuck repeating the same tool call",
                        extra={
                            "session_id": session_id,
                            "iteration": i,
                            "tool": tool_name,
                            "repeat_count": repeat_count,
                        },
                    )
                    final_result = {
                        "success": False,
                        "report": (
                            f"Agent appeared stuck: same {tool_name} call repeated "
                            f"{repeat_count} times in a row without progress."
                        ),
                    }
                    end_task_called = True  # break outer loop
                    break

                try:
                    result = self._dispatch_tool(tool_name, arguments, session_id=session_id)
                except Exception as e:  # pylint: disable=broad-except
                    result = f"ERROR executing {tool_name}: {str(e)}"
                    self.logger.error(
                        "Tool execution failed",
                        extra={"session_id": session_id, "tool": tool_name, "error": str(e)},
                    )

                messages.append(ToolMessage(
                    content=redact_secrets(str(result)),
                    tool_call_id=tc_id,
                    name=tool_name,
                ))

            if end_task_called:
                break

            # Check for steering messages injected by the parent agent
            # mid-execution. Each message is appended as a HumanMessage so
            # the LLM treats it as new user input that modifies/refines the
            # original instruction.
            steering_messages = self.session_manager.consume_steering_messages(session_id)
            for msg in steering_messages:
                self.logger.info(
                    "Injecting steering message",
                    extra={"session_id": session_id, "message_preview": msg[:200]},
                )
                messages.append(HumanMessage(content=f"[STEERING INSTRUCTION]: {msg}"))

        if final_result is None:
            final_result = {"success": False, "report": "Agent reached max iterations without calling end_task."}

        # Only files the agent EXPLICITLY listed in ``end_task(output_files=…)``
        # are forwarded to the bridge. Walking the workdir would dump every
        # scratch / cache / log file the agent left behind, which is exactly
        # what we don't want. The validation step rejects paths outside the
        # workdir or pointing at staged inputs.
        declared_output_files = list(final_result.get("output_files") or [])
        output_files = self._resolve_declared_output_files(
            workdir, declared_output_files, session_id=session_id,
        )
        processing_time = round(time.time() - start_time, 2)

        # Ensure the conversation history is well-formed before storing:
        # the OpenAI API requires that every AIMessage.tool_calls entry has a
        # matching ToolMessage with the same tool_call_id, and that no
        # ToolMessage exists without a preceding AIMessage that declares the
        # matching tool_call.  Patch dangling tool_calls and remove orphaned
        # ToolMessages so that restoring this history under
        # previous_session_id does not trigger a 400 error.
        messages = self._sanitize_messages(messages)

        # Store conversation history for potential correction re-dispatch.
        # While the agent loop is single-threaded, the session manager's lock
        # ensures safe access if another thread concurrently reads.
        try:
            self.session_manager.store_messages(
                session_id,
                self._serialize_messages(messages),
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning(
                "Failed to store messages",
                extra={"session_id": session_id, "error": str(exc)},
            )

        result_payload = {
            "session_id": session_id,
            "success": final_result.get("success", False),
            "report": redact_secrets(final_result.get("report", "")),
            "output_files": output_files,
            "processing_time_sec": processing_time,
        }
        self.logger.info("Agent loop finished", extra={"session_id": session_id, "success": result_payload["success"]})
        return result_payload
