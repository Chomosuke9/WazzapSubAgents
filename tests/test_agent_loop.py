from unittest.mock import MagicMock, patch

from src.agent import ExecutorAgent


def test_parse_tool_call_json():
    client = MagicMock()
    sm = MagicMock()
    agent = ExecutorAgent(client, sm)
    parsed = agent._parse_tool_call('{"tool": "bash", "arguments": {"command": "ls"}}')
    assert parsed["tool"] == "bash"


def test_parse_tool_call_markdown():
    client = MagicMock()
    sm = MagicMock()
    agent = ExecutorAgent(client, sm)
    parsed = agent._parse_tool_call('```json\n{"tool": "end_task", "arguments": {"success": true}}\n```')
    assert parsed["tool"] == "end_task"


def test_parse_tool_call_invalid():
    client = MagicMock()
    sm = MagicMock()
    agent = ExecutorAgent(client, sm)
    assert agent._parse_tool_call("not json") is None


@patch("src.agent.ChatAnthropic")
def test_execute_ends_on_end_task(mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "", "returncode": 0}
    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm

    # First response: bash, second: end_task
    responses = [
        MagicMock(content='{"tool": "bash", "arguments": {"command": "echo hi"}}'),
        MagicMock(content='{"tool": "end_task", "arguments": {"success": true, "report": "Done"}}'),
    ]
    mock_llm.invoke.side_effect = responses

    agent = ExecutorAgent(client, sm)
    result = agent.execute("s1", "do something", [], "/tmp/work/s1")
    assert result["success"] is True
    assert result["report"] == "Done"
    # verify progress was reported for the bash tool
    sm.append_progress.assert_called_once()


@patch("src.agent.ChatAnthropic")
def test_execute_max_iterations(mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm
    mock_llm.invoke.return_value = MagicMock(content='{"tool": "bash", "arguments": {"command": "echo hi"}}')

    agent = ExecutorAgent(client, sm)
    result = agent.execute("s1", "do something", [], "/tmp/work/s1")
    assert result["success"] is False
    assert "max iterations" in result["report"]
    # progress reported on each bash call (50 iterations)
    assert sm.append_progress.call_count == 50
