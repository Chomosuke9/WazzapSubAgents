import json
import os
import time
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

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
        self.llm = ChatOpenAI(
            model=config["agent_model"],
            temperature=config["agent_temperature"],
            api_key=config["llm_api_key"],
            **({"base_url": config["llm_base_url"]} if config["llm_base_url"] else {}),
        )
        self.tools = {
            "bash": self._bash_tool,
            "python": self._python_tool,
            "end_task": self._end_task_tool,
        }

    def _bash_tool(self, command: str, session_id: str) -> str:
        self.session_manager.append_progress(session_id, {
            "step": "bash",
            "detail": str({"command": command})[:500],
            "timestamp": time.time(),
        })
        result = self.container_client.run_bash(command, session_id=session_id)
        self.logger.info(
            "bash_tool executed",
            extra={
                "session_id": session_id,
                "command": command[:200],
                "returncode": result.get("returncode"),
            },
        )
        output = f"STDOUT:\n{result.get('stdout', '')}\nSTDERR:\n{result.get('stderr', '')}\nRETURNCODE: {result.get('returncode')}"
        return output

    def _python_tool(self, code: str, session_id: str) -> str:
        self.session_manager.append_progress(session_id, {
            "step": "python",
            "detail": str({"code": code})[:500],
            "timestamp": time.time(),
        })
        result = self.container_client.run_python(code, session_id=session_id)
        self.logger.info("python_tool executed", extra={"session_id": session_id, "code": code[:200]})
        if "error" in result:
            return f"ERROR:\n{result['error']}"
        return f"OUTPUT:\n{result.get('output', '')}"

    def _end_task_tool(self, success: bool, report: str, session_id: str) -> dict:
        self.logger.info("end_task_tool called", extra={"session_id": session_id, "success": success})
        return {"success": success, "report": report}

    def _collect_output_files(self, workdir: str) -> List[str]:
        # ``<workdir>/.inputs/`` is where ``stage_inputs_into_workdir`` places
        # caller-supplied input files so they are reachable inside the executor
        # sidecar. Those bytes were *received*, not *produced*, so excluding the
        # subtree prevents the bridge from echoing the same file back to the
        # user as a fresh "output".
        from src.input_staging import is_input_path

        files: list[str] = []
        if os.path.isdir(workdir):
            for root, _, filenames in os.walk(workdir):
                for f in filenames:
                    candidate = os.path.join(root, f)
                    if is_input_path(workdir, candidate):
                        continue
                    files.append(candidate)
        return files

    def _build_system_prompt(self, instruction: str, input_files: List[str], workdir: str) -> str:
        files_str = "\n".join(input_files) if input_files else "None"
        return (
            "You are an executor agent. Your job is to fulfill the user's instruction.\n"
            "You have access to the following tools:\n"
            "1. bash(command: str) - Execute a bash shell command.\n"
            "2. python(code: str) - Execute Python code.\n"
            "3. end_task(success: bool, report: str) - Finish the task and report results.\n\n"
            "Rules:\n"
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
            "will be filtered out of the result).\n\n"
            f"Workdir: {workdir}\n"
            f"Input files:\n{files_str}\n\n"
            f"Instruction: {instruction}\n\n"
            "Respond with a single JSON object containing 'tool' and 'arguments'.\n"
            'Example: {"tool": "bash", "arguments": {"command": "ls -la"}}\n'
            'Example: {"tool": "end_task", "arguments": {"success": true, "report": "Done"}}'
        )

    def _parse_tool_call(self, content: str) -> Optional[Dict[str, Any]]:
        # Try to extract JSON from the response
        content = content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    def _extract_tool_call(self, response: Any) -> Optional[Dict[str, Any]]:
        """Pick a tool call from the LLM response.

        Prefer native ``tool_calls`` produced by LangChain when the provider
        supports OpenAI-style function calling; fall back to JSON-in-content
        for providers / models that only emit raw text.
        """
        tool_calls = getattr(response, "tool_calls", None)
        if isinstance(tool_calls, list) and tool_calls:
            first = tool_calls[0]
            name = None
            args: Any = None
            if isinstance(first, dict):
                name = first.get("name") or (first.get("function") or {}).get("name")
                args = first.get("args")
                if args is None:
                    raw_args = (first.get("function") or {}).get("arguments")
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = None
                    elif isinstance(raw_args, dict):
                        args = raw_args
            else:
                name = getattr(first, "name", None)
                args = getattr(first, "args", None)
            if name:
                return {"tool": name, "arguments": args or {}}

        content = getattr(response, "content", None)
        if isinstance(content, list):
            content = "\n".join(str(c) for c in content)
        if not isinstance(content, str):
            return None
        return self._parse_tool_call(content)

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
                return self.llm.invoke(messages)
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

    def execute(
        self,
        session_id: str,
        instruction: str,
        input_files: List[str],
        workdir: str,
    ) -> Dict[str, Any]:
        start_time = time.time()
        self.logger.info("Agent loop starting", extra={"session_id": session_id})

        messages = [
            SystemMessage(content=self._build_system_prompt(instruction, input_files, workdir)),
        ]

        max_iterations = 50
        final_result: Optional[Dict[str, Any]] = None
        last_signature: Optional[str] = None
        repeat_count = 0

        for i in range(max_iterations):
            try:
                response = self._invoke_llm_with_retry(messages, session_id=session_id)
            except Exception as err:  # pylint: disable=broad-except
                final_result = {
                    "success": False,
                    "report": f"LLM invocation failed after retries: {err}",
                }
                break
            content = response.content
            if isinstance(content, list):
                content = "\n".join(str(c) for c in content)
            self.logger.info("LLM response", extra={"session_id": session_id, "iteration": i, "content": str(content)[:500]})

            tool_call = self._extract_tool_call(response)
            if not tool_call:
                # If LLM didn't return valid JSON, ask it to try again
                messages.append(AIMessage(content=content))
                messages.append(
                    HumanMessage(
                        content="Invalid format. Please respond with a single JSON object containing 'tool' and 'arguments'."
                    )
                )
                continue

            tool_name = tool_call.get("tool")
            arguments = tool_call.get("arguments", {}) or {}

            if tool_name not in self.tools:
                messages.append(AIMessage(content=content))
                messages.append(HumanMessage(content=f"Tool '{tool_name}' not available. Use bash, python, or end_task."))
                continue

            if tool_name == "end_task":
                final_result = self.tools[tool_name](**arguments, session_id=session_id)
                break

            # Track repeated identical tool calls so we can break out of obvious loops.
            try:
                signature = json.dumps({"tool": tool_name, "arguments": arguments}, sort_keys=True, default=str)
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
                break

            # Execute bash or python
            try:
                result = self.tools[tool_name](**arguments, session_id=session_id)
            except Exception as e:
                result = f"ERROR executing {tool_name}: {str(e)}"
                self.logger.error("Tool execution failed", extra={"session_id": session_id, "tool": tool_name, "error": str(e)})

            messages.append(AIMessage(content=content))
            messages.append(HumanMessage(content=f"Result of {tool_name}:\n{result}"))

        if final_result is None:
            final_result = {"success": False, "report": "Agent reached max iterations without calling end_task."}

        output_files = self._collect_output_files(workdir)
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
