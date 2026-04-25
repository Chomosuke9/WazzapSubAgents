import json
import os
import time
from typing import Any, Dict, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from src.config import config
from src.container_client import ContainerClient
from src.logger import get_logger
from src.session_manager import SessionManager

logger = get_logger(__name__)


class ExecutorAgent:
    def __init__(self, container_client: ContainerClient, session_manager: SessionManager, logger_override=None):
        self.container_client = container_client
        self.session_manager = session_manager
        self.logger = logger_override or logger
        self.llm = ChatAnthropic(
            model=config["agent_model"],
            temperature=config["agent_temperature"],
            max_tokens=config["agent_max_tokens"],
            anthropic_api_key=config["llm_api_key"],
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
        files = []
        if os.path.isdir(workdir):
            for root, _, filenames in os.walk(workdir):
                for f in filenames:
                    files.append(os.path.join(root, f))
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
            "- Input files are at the paths provided below.\n"
            "- Write output files to the workdir if needed.\n\n"
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

        for i in range(max_iterations):
            response = self.llm.invoke(messages)
            content = response.content
            if isinstance(content, list):
                content = "\n".join(str(c) for c in content)
            self.logger.info("LLM response", extra={"session_id": session_id, "iteration": i, "content": content[:500]})

            tool_call = self._parse_tool_call(content)
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
            arguments = tool_call.get("arguments", {})

            if tool_name not in self.tools:
                messages.append(AIMessage(content=content))
                messages.append(HumanMessage(content=f"Tool '{tool_name}' not available. Use bash, python, or end_task."))
                continue

            if tool_name == "end_task":
                final_result = self.tools[tool_name](**arguments, session_id=session_id)
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
