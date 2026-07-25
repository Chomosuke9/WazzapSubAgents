from src.prompts import build_executor_system_prompt, load_skill_catalog


def test_system_prompt_injects_catalog_and_skips_redundant_readme_call():
    load_skill_catalog.cache_clear()
    prompt = build_executor_system_prompt("/tmp/session")

    assert "9router:" in prompt
    assert "/skills/9router/SKILL.md" in prompt
    assert "do not spend a tool call rereading `/skills/README.md`" in prompt
    assert "Workdir: /tmp/session" in prompt
