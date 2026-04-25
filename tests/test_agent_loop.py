from unittest.mock import MagicMock, patch

from src.agent import ExecutorAgent


def _make_response(tool_calls=None, content=""):
    """Build a minimal LangChain-style response object for tests.

    ``tool_calls`` follows the dict shape LangChain emits in modern versions
    (``{"name", "args", "id"}``) so the agent's normaliser sees a stable
    ``id`` for the matching ``ToolMessage``.
    """
    response = MagicMock()
    response.content = content
    response.tool_calls = tool_calls or []
    return response


def _bash_tc(reason="reason", command="echo hi", call_id="call_bash_1"):
    return {"name": "bash", "args": {"reason": reason, "command": command}, "id": call_id}


def _end_tc(success=True, report="Done", call_id="call_end_1"):
    return {
        "name": "end_task",
        "args": {"success": success, "report": report},
        "id": call_id,
    }


@patch("src.agent.ChatOpenAI")
def test_normalize_tool_calls_dict(mock_llm_class):
    agent = ExecutorAgent(MagicMock(), MagicMock())
    response = _make_response([_end_tc()])
    parsed = agent._normalize_tool_calls(response)
    assert parsed == [
        {"name": "end_task", "args": {"success": True, "report": "Done"}, "id": "call_end_1"}
    ]


@patch("src.agent.ChatOpenAI")
def test_normalize_tool_calls_function_arguments_string(_mock_llm_class):
    """Some providers emit OpenAI's function/arguments string format."""
    agent = ExecutorAgent(MagicMock(), MagicMock())
    response = _make_response([
        {
            "id": "call_x",
            "function": {"name": "bash", "arguments": '{"reason": "ls", "command": "ls"}'},
        }
    ])
    parsed = agent._normalize_tool_calls(response)
    assert parsed[0]["name"] == "bash"
    assert parsed[0]["args"] == {"reason": "ls", "command": "ls"}
    assert parsed[0]["id"] == "call_x"


@patch("src.agent.ChatOpenAI")
def test_normalize_tool_calls_empty_when_no_tool_calls(_mock_llm_class):
    agent = ExecutorAgent(MagicMock(), MagicMock())
    response = _make_response(tool_calls=None, content="just text")
    assert agent._normalize_tool_calls(response) == []


@patch("src.agent.ChatOpenAI")
def test_execute_ends_on_end_task(mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "", "returncode": 0}
    mock_llm = MagicMock()
    mock_llm_class.return_value.bind_tools.return_value = mock_llm

    # First response: bash, second: end_task. Both via native tool_calls.
    mock_llm.invoke.side_effect = [
        _make_response([_bash_tc("Run echo", "echo hi", "tc-1")]),
        _make_response([_end_tc(True, "Done", "tc-2")]),
    ]

    agent = ExecutorAgent(client, sm)
    result = agent.execute("s1", "do something", [], "/tmp/work/s1")
    assert result["success"] is True
    assert result["report"] == "Done"
    # The bash tool reported one progress entry.
    sm.append_progress.assert_called_once()


@patch("src.agent.ChatOpenAI")
def test_execute_max_iterations(mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "", "returncode": 0}
    mock_llm = MagicMock()
    mock_llm_class.return_value.bind_tools.return_value = mock_llm
    # Vary the command each turn so the stuck-loop detector does not trip
    # before the 50-iteration cap.
    mock_llm.invoke.side_effect = [
        _make_response([_bash_tc(f"step {i}", f"echo {i}", f"tc-{i}")])
        for i in range(60)
    ]

    agent = ExecutorAgent(client, sm)
    result = agent.execute("s1", "do something", [], "/tmp/work/s1")
    assert result["success"] is False
    assert "max iterations" in result["report"]
    assert sm.append_progress.call_count == 50


@patch("src.agent.ChatOpenAI")
def test_execute_stops_on_stuck_loop(mock_llm_class):
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "", "returncode": 0}
    mock_llm = MagicMock()
    mock_llm_class.return_value.bind_tools.return_value = mock_llm
    # Every turn emits the SAME bash call (same args). The stuck-loop
    # detector should kick in after STUCK_LOOP_THRESHOLD repeats.
    mock_llm.invoke.return_value = _make_response(
        [_bash_tc("loop", "echo hi", "tc-loop")]
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
    mock_llm_class.return_value.bind_tools.return_value = mock_llm

    class _RateLimitError(Exception):
        status_code = 429

    success_response = _make_response([_end_tc(True, "ok", "tc-ok")])
    mock_llm.invoke.side_effect = [
        _RateLimitError("429"),
        _RateLimitError("429"),
        success_response,
    ]

    agent = agent_module.ExecutorAgent(client, sm)
    result = agent.execute("s3", "do something", [], "/tmp/work/s3")
    assert result["success"] is True
    assert result["report"] == "ok"
    assert mock_llm.invoke.call_count == 3


@patch("src.agent.ChatOpenAI")
def test_execute_retries_when_llm_returns_plain_text(mock_llm_class, monkeypatch):
    """If the LLM forgets to emit a tool_call we re-invoke at the same turn
    rather than appending the bad text to history. After NO_TOOL_RETRY_MAX
    failed attempts the agent gives up gracefully."""
    import src.agent as agent_module

    monkeypatch.setattr(agent_module, "NO_TOOL_RETRY_MAX", 2)

    client = MagicMock()
    sm = MagicMock()
    mock_llm = MagicMock()
    mock_llm_class.return_value.bind_tools.return_value = mock_llm

    plain = _make_response(content="I am thinking out loud", tool_calls=None)
    success = _make_response([_end_tc(True, "finally", "tc-finally")])
    # Two plain-text replies, then a real tool_call.
    mock_llm.invoke.side_effect = [plain, plain, success]

    agent = agent_module.ExecutorAgent(client, sm)
    result = agent.execute("s4", "do something", [], "/tmp/work/s4")
    assert result["success"] is True
    assert result["report"] == "finally"
    # Three invokes total — the two retries did NOT pollute the message
    # history with the bad AIMessage (otherwise the third invoke would
    # double-down on the same plain-text mistake).
    assert mock_llm.invoke.call_count == 3


@patch("src.agent.ChatOpenAI")
def test_execute_gives_up_after_no_tool_retries(mock_llm_class, monkeypatch):
    import src.agent as agent_module

    monkeypatch.setattr(agent_module, "NO_TOOL_RETRY_MAX", 2)

    client = MagicMock()
    sm = MagicMock()
    mock_llm = MagicMock()
    mock_llm_class.return_value.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = _make_response(content="still no tool", tool_calls=None)

    agent = agent_module.ExecutorAgent(client, sm)
    result = agent.execute("s5", "do something", [], "/tmp/work/s5")
    assert result["success"] is False
    assert "tool_call" in result["report"]
    # NO_TOOL_RETRY_MAX + 1 attempts, then we bail out.
    assert mock_llm.invoke.call_count == 3


@patch("src.agent.ChatOpenAI")
def test_execute_passes_reason_to_progress(mock_llm_class):
    """End-to-end check that the ``reason`` arg propagates to append_progress
    so the bridge can show *why* each step ran."""
    client = MagicMock()
    sm = MagicMock()
    client.run_bash.return_value = {"stdout": "", "stderr": "", "returncode": 0}
    mock_llm = MagicMock()
    mock_llm_class.return_value.bind_tools.return_value = mock_llm
    mock_llm.invoke.side_effect = [
        _make_response([_bash_tc("Mengekstrak zip yang diterima", "unzip foo.zip", "tc-1")]),
        _make_response([_end_tc(True, "ok", "tc-2")]),
    ]

    agent = ExecutorAgent(client, sm)
    agent.execute("s6", "extract zip", [], "/tmp/work/s6")
    sm.append_progress.assert_called_once()
    progress = sm.append_progress.call_args[0][1]
    assert progress["step"] == "bash"
    assert "Mengekstrak zip" in progress["reason"]


def _make_resolver_agent():
    """Build a bare ``ExecutorAgent`` for tests that exercise
    ``_resolve_declared_output_files`` directly without bringing up the
    full agent loop."""
    client = MagicMock()
    sm = MagicMock()
    with patch("src.agent.ChatOpenAI"):
        return ExecutorAgent(client, sm)


def test_resolve_declared_output_files_only_returns_declared_paths(tmp_path):
    """The agent must only ship files it explicitly listed in ``end_task``.
    Scratch / cache / log files left lying around in the workdir must
    NOT be auto-collected."""
    workdir = tmp_path / "session-x"
    workdir.mkdir()
    deliverable = workdir / "report.pdf"
    deliverable.write_bytes(b"%PDF-fake")
    # Scratch files the agent left behind (cache, logs, intermediates).
    (workdir / "scratch.tmp").write_text("intermediate")
    (workdir / "pip-cache.log").write_text("log")
    (workdir / "intermediate.bin").write_bytes(b"\x00")

    agent = _make_resolver_agent()
    accepted = agent._resolve_declared_output_files(
        str(workdir), [str(deliverable)], session_id="s1",
    )

    assert accepted == [str(deliverable.resolve())]


def test_resolve_declared_output_files_rejects_input_paths(tmp_path):
    """Paths inside ``<workdir>/.inputs/`` must be dropped — those are
    caller-supplied inputs and re-shipping them would dupe the user's
    own file as a fresh deliverable."""
    from src.input_staging import INPUT_SUBDIR

    workdir = tmp_path / "session-x"
    workdir.mkdir()
    inputs = workdir / INPUT_SUBDIR
    inputs.mkdir()
    user_doc = inputs / "user-doc.zip"
    user_doc.write_bytes(b"input-bytes")
    legit_output = workdir / "extracted.txt"
    legit_output.write_text("hello")

    agent = _make_resolver_agent()
    accepted = agent._resolve_declared_output_files(
        str(workdir), [str(user_doc), str(legit_output)], session_id="s1",
    )

    assert accepted == [str(legit_output.resolve())]


def test_resolve_declared_output_files_rejects_paths_outside_workdir(tmp_path):
    """The validator must refuse paths outside the workdir even if they
    exist — a misbehaving agent shouldn't be able to exfiltrate
    arbitrary host files via the output channel."""
    workdir = tmp_path / "session-x"
    workdir.mkdir()
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("not yours")
    inside = workdir / "ok.txt"
    inside.write_text("yours")

    agent = _make_resolver_agent()
    accepted = agent._resolve_declared_output_files(
        str(workdir), [str(outside), str(inside)], session_id="s1",
    )

    assert accepted == [str(inside.resolve())]


def test_resolve_declared_output_files_drops_missing_and_dirs(tmp_path):
    """Non-existent paths and directories must be dropped — only regular
    files are valid deliverables."""
    workdir = tmp_path / "session-x"
    workdir.mkdir()
    (workdir / "subdir").mkdir()
    real_file = workdir / "ok.txt"
    real_file.write_text("real")

    agent = _make_resolver_agent()
    accepted = agent._resolve_declared_output_files(
        str(workdir),
        [
            str(workdir / "ghost.txt"),  # missing
            str(workdir / "subdir"),  # directory
            str(real_file),
        ],
        session_id="s1",
    )

    assert accepted == [str(real_file.resolve())]


def test_resolve_declared_output_files_returns_empty_for_empty_input(tmp_path):
    """An empty / omitted ``output_files`` list must result in an empty
    list — this is the calculator-only case where the agent has nothing
    to ship."""
    workdir = tmp_path / "session-x"
    workdir.mkdir()
    # Some scratch left around — must NOT auto-leak even though the list
    # is empty.
    (workdir / "scratch.tmp").write_text("nope")

    agent = _make_resolver_agent()
    assert agent._resolve_declared_output_files(str(workdir), [], session_id="s1") == []


def test_end_task_dispatch_normalizes_output_files():
    """The ``end_task`` dispatch path must normalise weird inputs (None,
    non-list, non-string entries) into a clean list-of-strings rather
    than crashing the agent loop."""
    agent = _make_resolver_agent()

    # None / missing -> []
    out = agent._dispatch_tool(
        "end_task", {"success": True, "report": "ok"}, session_id="s1",
    )
    assert out == {"success": True, "report": "ok", "output_files": []}

    # Non-list -> [] with a warning logged
    out = agent._dispatch_tool(
        "end_task",
        {"success": True, "report": "ok", "output_files": "not-a-list"},
        session_id="s1",
    )
    assert out["output_files"] == []

    # Mixed list -> only non-empty strings survive
    out = agent._dispatch_tool(
        "end_task",
        {
            "success": True,
            "report": "ok",
            "output_files": ["/tmp/a", 42, "", "  ", "/tmp/b"],
        },
        session_id="s1",
    )
    assert out["output_files"] == ["/tmp/a", "/tmp/b"]
