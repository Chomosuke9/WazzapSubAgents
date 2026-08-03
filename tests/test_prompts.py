from src.prompts import build_executor_system_prompt


def test_system_prompt_injects_input_files_and_skips_redundant_readme_call():
    prompt = build_executor_system_prompt("/tmp/session", ["/input/a.pdf", "/input/b.txt"])

    assert "not spend a tool call rereading `/skills/README.md`" not in prompt
    assert "9router:" not in prompt
    assert "- Catalog unavailable;" not in prompt
    assert "Input files (read them from these exact paths):" in prompt
    assert "- /input/a.pdf" in prompt
    assert "- /input/b.txt" in prompt
    assert "Your FIRST tool call for every task must inspect" in prompt
    assert "After a task succeeds through the skills/fallback route" in prompt
    assert "Do not write a method for a failed or partially completed task" in prompt
    assert "not the request's topic, entity, location, brand, or visual theme" in prompt
    assert "create a new file only for a material procedural difference" in prompt
    assert "a tested one-line command" in prompt
    assert "independent validation command with expected checking output" in prompt
    assert "python -m pip install --target /dependencies/python" in prompt
    assert "npm install --prefix /dependencies/node" in prompt
    assert "prefer a pinned prebuilt/static artifact" in prompt
    assert "do not build it from source" in prompt
    assert "verify its published checksum or signature when available" in prompt
    assert "If no trustworthy compatible prebuilt artifact is available" in prompt
    assert "never use `apt`, `apk`, or another OS package manager" in prompt
    assert prompt.index("Reusable methods") < prompt.index("Technical documentation fallback")
    assert "Input files (read them from these exact paths):" in prompt
    assert "Workdir: /tmp/session" in prompt


def test_system_prompt_handles_empty_input_files():
    prompt = build_executor_system_prompt("/tmp/session", [])

    assert "- (none)" in prompt
    assert "/tmp/session" in prompt