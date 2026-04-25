import json
import os
import time
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.config import config
from src.container_client import ContainerClient
from src.logger import get_logger
from src.session_manager import SessionManager

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
            "Execute a bash shell command inside the executor sidecar. "
            "Use this for file operations, installations, and running "
            "external programs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Short explanation (1 sentence) of WHY you are "
                        "running this command, e.g. 'Mengekstrak zip yang "
                        "diterima'. Surfaced as a progress update to the "
                        "bridge."
                    ),
                    "minLength": 1,
                },
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                    "minLength": 1,
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
            "Execute Python code inside the executor sidecar. "
            "Use this for data processing, parsing, and calculations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Short explanation (1 sentence) of WHY you are "
                        "running this code, e.g. 'Parsing PDF jadi JSON'. "
                        "Surfaced as a progress update to the bridge."
                    ),
                    "minLength": 1,
                },
                "code": {
                    "type": "string",
                    "description": "The Python source code to execute.",
                    "minLength": 1,
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
            "Finish the task and report results back to the caller. Call "
            "this exactly once when the instruction is fully resolved or "
            "cannot be completed."
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
                        "Optional. Absolute paths of files YOU explicitly want "
                        "to send back to the user. Only list files that are "
                        "actually meant as deliverables — never temp / cache / "
                        "log / intermediate files. Omit entirely (or pass []) "
                        "when the task does not produce a file to share (e.g. "
                        "a calculation, a yes/no answer). Paths must live "
                        "inside the workdir; anything in `.inputs/` is "
                        "rejected because those are caller-supplied inputs."
                    ),
                },
            },
            "required": ["success", "report"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    BASH_TOOL_SCHEMA,
    PYTHON_TOOL_SCHEMA,
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
        base_llm = ChatOpenAI(
            model=config["agent_model"],
            temperature=config["agent_temperature"],
            api_key=config["llm_api_key"],
            **({"base_url": config["llm_base_url"]} if config["llm_base_url"] else {}),
        )
        # Bind the tool schemas once so every invocation reuses the same
        # ``Runnable`` and the model is forced to emit native ``tool_calls``
        # instead of JSON-in-content.
        self.llm = base_llm.bind_tools(TOOL_SCHEMAS)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------
    def _bash_tool(self, reason: str, command: str, session_id: str) -> str:
        self.session_manager.append_progress(session_id, {
            "step": "bash",
            "reason": (reason or "")[:500],
            "detail": str({"reason": reason, "command": command})[:500],
            "timestamp": time.time(),
        })
        result = self.container_client.run_bash(command, session_id=session_id)
        self.logger.info(
            "bash_tool executed",
            extra={
                "session_id": session_id,
                "reason": (reason or "")[:200],
                "command": command[:200],
                "returncode": result.get("returncode"),
            },
        )
        output = f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}\nRETURNCODE: {result.get('returncode')}"
        return output

    def _python_tool(self, reason: str, code: str, session_id: str) -> str:
        self.session_manager.append_progress(session_id, {
            "step": "python",
            "reason": (reason or "")[:500],
            "detail": str({"reason": reason, "code": code})[:500],
            "timestamp": time.time(),
        })
        result = self.container_client.run_python(code, session_id=session_id)
        self.logger.info(
            "python_tool executed",
            extra={
                "session_id": session_id,
                "reason": (reason or "")[:200],
                "code": code[:200],
            },
        )
        if "error" in result:
            return f"ERROR:\n{result['error']}"
        return f"OUTPUT:\n{result.get('output', '')}"

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
            )
        if tool_name == "python":
            return self._python_tool(
                reason=arguments.get("reason", ""),
                code=arguments.get("code", ""),
                session_id=session_id,
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
        - sit inside ``workdir`` (no traversal outside the sandbox),
        - are NOT inside ``<workdir>/.inputs/`` (those are caller-supplied
          inputs — echoing them back would dupe the user's own file as a
          fresh "deliverable").

        Anything else is dropped with a logged warning. Returning a strict
        subset (rather than failing the whole task) lets the user still get
        the textual report when the model lists a couple of bogus paths.
        """
        from src.input_staging import is_input_path

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

            if is_input_path(workdir, resolved):
                skipped.append({"path": raw_path, "reason": "is_input_file"})
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

        return accepted

    def _build_system_prompt(self, instruction: str, input_files: List[str], workdir: str) -> str:
        files_str = "\n".join(input_files) if input_files else "None"
        return (
            "You are an executor agent. Your job is to fulfill the user's "
            "instruction by calling the provided tools.\n\n"
            "Tools available (call exactly one per turn — never reply with "
            "plain text, always invoke a tool):\n"
            "1. bash(reason, command) — run a bash command.\n"
            "2. python(reason, code) — run Python code.\n"
            "3. end_task(success, report) — finish the task with a final report.\n\n"
            "Rules:\n"
            "- The `reason` argument is REQUIRED on `bash` and `python`. Keep "
            "  it short (one sentence) and explain WHY you are running this "
            "  step. It is shown back to the orchestrating agent as a "
            "  progress update.\n"
            "- Use bash for file operations, installations, running external programs.\n"
            "- Use python for data processing, parsing, calculations.\n"
            "- If a tool returns an error, decide whether to retry, pivot, or fail.\n"
            "- Do not ask the user questions. Decide and act.\n"
            "- Input files are at the EXACT paths provided below — they have "
            "already been staged inside the workdir for you. Use those paths "
            "verbatim in `bash`/`python`. Do NOT search the filesystem for "
            "alternative locations and do NOT invent new paths.\n"
            "- Write output files anywhere inside the workdir EXCEPT the "
            "`.inputs/` subdirectory (those are caller-supplied inputs and "
            "will be rejected if you try to ship them back).\n"
            "- When the instruction is fully resolved (or cannot be done), "
            "call `end_task` exactly once and stop.\n"
            "- `end_task` accepts an OPTIONAL `output_files` list. Only "
            "include paths of files that are deliverables for the user "
            "(e.g. an extracted `report.pdf`, a generated chart). Skip the "
            "argument entirely (or pass `[]`) for tasks that don't produce "
            "a file (e.g. answering a question, doing a calculation). NEVER "
            "list scratch / temp / cache / log / intermediate files — the "
            "user only wants the final deliverable, not your workspace.\n\n"
            f"Workdir: {workdir}\n"
            f"Input files:\n{files_str}\n\n"
            f"Instruction: {instruction}"
        )

    # ------------------------------------------------------------------
    # Tool-call extraction
    # ------------------------------------------------------------------
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
    def _invoke_llm_with_retry(self, messages: List[Any], session_id: str) -> Any:
        """Call the LLM with bounded retries for transient errors.

        A single transient failure (rate limit, network blip, 5xx) used to
        kill the entire sub-task. We now retry up to ``LLM_RETRY_MAX`` times
        with exponential backoff, honouring ``Retry-After`` when given.
        """
        attempts = max(1, LLM_RETRY_MAX + 1)
        last_err: Optional[BaseException] = None
        for attempt in range(1, attempts + 1):
            try:
                self.logger.debug(
                    "About to invoke LLM",
                    extra={
                        "session_id": session_id,
                        "messages_count": len(messages),
                        "last_message_role": messages[-1].get("role") if messages else None,
                    },
                )
                response = self.llm.invoke(messages)
                print("Response type:", type(response))
                print("Has tool_calls attr?", hasattr(response, "tool_calls"))

                if hasattr(response, "tool_calls"):
                    print("tool_calls:", response.tool_calls)
                    if response.tool_calls:
                        print("First tool_call:", response.tool_calls[0])
                        print("First tool_call type:", type(response.tool_calls[0]))
                        print("First tool_call dir:", [x for x in dir(response.tool_calls[0]) if not x.startswith('_')])
                return response
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
            response = self._invoke_llm_with_retry(messages, session_id=session_id)
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
    # Main agent loop
    # ------------------------------------------------------------------
    def execute(
        self,
        session_id: str,
        instruction: str,
        input_files: List[str],
        workdir: str,
    ) -> Dict[str, Any]:
        start_time = time.time()
        self.logger.info("Agent loop starting", extra={"session_id": session_id})

        messages: List[Any] = [
            SystemMessage(content=self._build_system_prompt(instruction, input_files, workdir)),
            HumanMessage(content="Begin executing the instruction."),
        ]

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

                if tool_name not in {"bash", "python"}:
                    messages.append(ToolMessage(
                        content=f"Tool '{tool_name}' is not available. Use bash, python, or end_task.",
                        tool_call_id=tc_id,
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
                    content=str(result),
                    tool_call_id=tc_id,
                ))

            if end_task_called:
                break

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

        result_payload = {
            "session_id": session_id,
            "success": final_result.get("success", False),
            "report": final_result.get("report", ""),
            "output_files": output_files,
            "processing_time_sec": processing_time,
        }
        self.logger.info("Agent loop finished", extra={"session_id": session_id, "success": result_payload["success"]})
        return result_payload
