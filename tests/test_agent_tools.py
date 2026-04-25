from unittest.mock import MagicMock, patch

from src.agent import ExecutorAgent


@patch("src.agent.ChatOpenAI")
def test_bash_tool(_mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "hello", "stderr": "", "returncode": 0}
    agent = ExecutorAgent(client, sm)
    result = agent._bash_tool("Listing files", "echo hello", "s1")
    assert "STDOUT:\nhello" in result
    assert "RETURNCODE: 0" in result
    sm.append_progress.assert_called_once()
    progress = sm.append_progress.call_args[0][1]
    assert progress["step"] == "bash"
    assert "Listing files" in progress["reason"]


@patch("src.agent.ChatOpenAI")
def test_bash_tool_error(_mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "error", "returncode": 1}
    agent = ExecutorAgent(client, sm)
    result = agent._bash_tool("Triggering failure", "false", "s1")
    assert "RETURNCODE: 1" in result


@patch("src.agent.ChatOpenAI")
def test_python_tool(_mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_python.return_value = {"output": "42"}
    agent = ExecutorAgent(client, sm)
    result = agent._python_tool("Compute the answer", "print(42)", "s1")
    assert "OUTPUT:\n42" in result
    sm.append_progress.assert_called_once()
    progress = sm.append_progress.call_args[0][1]
    assert progress["step"] == "python"
    assert "Compute the answer" in progress["reason"]


@patch("src.agent.ChatOpenAI")
def test_python_tool_error(_mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_python.return_value = {"error": "SyntaxError"}
    agent = ExecutorAgent(client, sm)
    result = agent._python_tool("Try bad code", "bad code", "s1")
    assert "ERROR:\nSyntaxError" in result


@patch("src.agent.ChatOpenAI")
def test_end_task_tool(_mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    agent = ExecutorAgent(client, sm)
    result = agent._end_task_tool(True, "Done", "s1")
    assert result["success"] is True
    assert result["report"] == "Done"
