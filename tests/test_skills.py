import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_9ROUTER_SKILLS = {
    "9router",
    "9router-chat",
    "9router-embeddings",
    "9router-image",
    "9router-stt",
    "9router-tts",
    "9router-video",
    "9router-web-fetch",
    "9router-web-search",
}


def test_all_9router_skills_are_installed_with_matching_frontmatter():
    for name in EXPECTED_9ROUTER_SKILLS:
        path = PROJECT_ROOT / "skills" / "9router"
        if name != "9router":
            path /= name
        path /= "SKILL.md"
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^name:\s*(\S+)\s*$", text)
        assert match is not None
        assert match.group(1) == name


def test_9router_entry_links_every_local_capability():
    text = (PROJECT_ROOT / "skills" / "9router" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for name in EXPECTED_9ROUTER_SKILLS - {"9router"}:
        assert f"/skills/9router/{name}/SKILL.md" in text
    assert "raw.githubusercontent.com" not in text


def test_create_method_skill_is_installed_and_catalogued():
    path = PROJECT_ROOT / "skills" / "create-method" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    catalog = (PROJECT_ROOT / "skills" / "README.md").read_text(encoding="utf-8")

    assert re.search(r"(?m)^name:\s*create-method\s*$", text)
    assert "objectively validated successful task" in text
    assert "Do not write anything when the task failed" in text
    assert "## One line command" in text
    assert "## Expected result" in text
    assert "Expected output:" in text
    assert "single physical, copy-pasteable line" in text
    assert "Never present a newly compressed, untested command as proven" in text
    assert "Atomically rename" in text
    assert "Never include a method file in `output_files`" in text
    assert "[create-method](./create-method)" in catalog
