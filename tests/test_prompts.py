from src.prompts import build_executor_system_prompt, load_skill_catalog


def test_system_prompt_injects_catalog_and_skips_redundant_readme_call():
    prompt = build_executor_system_prompt("/tmp/session")

    assert "9router:" in prompt
    assert "/skills/9router/SKILL.md" in prompt
    assert "create-method:" in prompt
    assert "read `/skills/create-method/SKILL.md`" in prompt
    assert "do not spend a tool call rereading `/skills/README.md`" in prompt
    assert "Your FIRST tool call for every task must inspect" in prompt
    assert "After a task succeeds through the skills/fallback route" in prompt
    assert "Do not write a method for a failed or partially completed task" in prompt
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
    assert "Workdir: /tmp/session" in prompt


def test_skill_catalog_reflects_bind_mount_changes_without_restart(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    monkeypatch.setenv("SKILLS_DIR", str(tmp_path))
    readme.write_text(
        "| Folder | Description |\n|---|---|\n| [first](./first) | First skill. |\n",
        encoding="utf-8",
    )
    assert "first: First skill." in load_skill_catalog()

    readme.write_text(
        "| Folder | Description |\n|---|---|\n| [second](./second) | Second skill. |\n",
        encoding="utf-8",
    )
    catalog = load_skill_catalog()
    assert "second: Second skill." in catalog
    assert "first: First skill." not in catalog
