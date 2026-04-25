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


@patch("src.agent.ChatOpenAI")
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


@patch("src.agent.ChatOpenAI")
def test_execute_max_iterations(mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm
    # Vary the command each turn so the stuck-loop detector does not trip
    # before the 50-iteration cap.
    mock_llm.invoke.side_effect = [
        MagicMock(content=f'{{"tool": "bash", "arguments": {{"command": "echo {i}"}}}}')
        for i in range(60)
    ]

    agent = ExecutorAgent(client, sm)
    result = agent.execute("s1", "do something", [], "/tmp/work/s1")
    assert result["success"] is False
    assert "max iterations" in result["report"]
    # progress reported on each bash call (50 iterations)
    assert sm.append_progress.call_count == 50


@patch("src.agent.ChatOpenAI")
def test_execute_stops_on_stuck_loop(mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "", "returncode": 0}
    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm
    mock_llm.invoke.return_value = MagicMock(
        content='{"tool": "bash", "arguments": {"command": "echo hi"}}'
    )

    agent = ExecutorAgent(client, sm)
    result = agent.execute("s2", "do something", [], "/tmp/work/s2")
    assert result["success"] is False
    assert "stuck" in result["report"].lower()
    # The 5th identical call trips the detector before its bash runs, so the
    # tool itself only executes 4 times.
    assert sm.append_progress.call_count == 4


@patch("src.agent.ChatOpenAI")
def test_execute_retries_transient_llm_error(mock_llm_class, monkeypatch):
    """Rate-limit / 5xx during llm.invoke should retry, not kill the task."""
    import src.agent as agent_module

    monkeypatch.setattr(agent_module, "LLM_RETRY_BASE_BACKOFF", 0.0)
    monkeypatch.setattr(agent_module, "LLM_RETRY_MAX_BACKOFF", 0.0)
    monkeypatch.setattr(agent_module, "LLM_RETRY_MAX", 5)

    client = MagicMock()
    sm = MagicMock()
    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm

    class _RateLimitError(Exception):
        status_code = 429

    success_response = MagicMock(
        content='{"tool": "end_task", "arguments": {"success": true, "report": "ok"}}'
    )
    mock_llm.invoke.side_effect = [_RateLimitError("429"), _RateLimitError("429"), success_response]

    agent = agent_module.ExecutorAgent(client, sm)
    result = agent.execute("s3", "do something", [], "/tmp/work/s3")
    assert result["success"] is True
    assert result["report"] == "ok"
    assert mock_llm.invoke.call_count == 3


@patch("src.agent.ChatOpenAI")
def test_execute_extracts_native_tool_calls(mock_llm_class):
    """LangChain-style ``tool_calls`` should be preferred over JSON-in-content."""
    client = MagicMock()
    sm = MagicMock()
    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm
    response = MagicMock(content="")
    response.tool_calls = [{"name": "end_task", "args": {"success": True, "report": "native"}}]
    mock_llm.invoke.return_value = response

    agent = ExecutorAgent(client, sm)
    result = agent.execute("s4", "do something", [], "/tmp/work/s4")
    assert result["success"] is True
    assert result["report"] == "native"


def test_collect_output_files_excludes_inputs_subdir(tmp_path):
    """Files staged into ``<workdir>/.inputs/`` must NOT show up in
    ``output_files`` — otherwise the bridge would echo every input back to
    the user as a fresh output."""
    from src.input_staging import INPUT_SUBDIR

    workdir = tmp_path / "session-x"
    workdir.mkdir()
    # Outputs the agent "produced".
    (workdir / "result.txt").write_text("real output")
    nested = workdir / "subdir"
    nested.mkdir()
    (nested / "nested.bin").write_bytes(b"\x00\x01")
    # Inputs that were staged in by the bridge.
    inputs = workdir / INPUT_SUBDIR
    inputs.mkdir()
    (inputs / "user-doc.zip").write_bytes(b"input-bytes")
    (inputs / "another.pdf").write_bytes(b"another")

    client = MagicMock()
    sm = MagicMock()
    agent = ExecutorAgent(client, sm)

    collected = agent._collect_output_files(str(workdir))
    basenames = sorted(p.split("/")[-1] for p in collected)
    assert "result.txt" in basenames
    assert "nested.bin" in basenames
    # The two input files must be filtered out.
    assert "user-doc.zip" not in basenames
    assert "another.pdf" not in basenames
