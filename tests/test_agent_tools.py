from unittest.mock import MagicMock

from src.agent import ExecutorAgent


def test_bash_tool():
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "hello", "stderr": "", "returncode": 0}
    agent = ExecutorAgent(client, sm)
    result = agent._bash_tool("echo hello", "s1")
    assert "STDOUT:\nhello" in result
    assert "RETURNCODE: 0" in result
    sm.append_progress.assert_called_once()


def test_bash_tool_error():
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "error", "returncode": 1}
    agent = ExecutorAgent(client, sm)
    result = agent._bash_tool("false", "s1")
    assert "RETURNCODE: 1" in result


def test_python_tool():
    client = MagicMock()
    sm = MagicMock()
    client.run_python.return_value = {"output": "42"}
    agent = ExecutorAgent(client, sm)
    result = agent._python_tool("print(42)", "s1")
    assert "OUTPUT:\n42" in result
    sm.append_progress.assert_called_once()


def test_python_tool_error():
    client = MagicMock()
    sm = MagicMock()
    client.run_python.return_value = {"error": "SyntaxError"}
    agent = ExecutorAgent(client, sm)
    result = agent._python_tool("bad code", "s1")
    assert "ERROR:\nSyntaxError" in result


def test_end_task_tool():
    client = MagicMock()
    sm = MagicMock()
    agent = ExecutorAgent(client, sm)
    result = agent._end_task_tool(True, "Done", "s1")
    assert result["success"] is True
    assert result["report"] == "Done"
