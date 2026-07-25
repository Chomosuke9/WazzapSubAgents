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
        path = PROJECT_ROOT / "skills" / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^name:\s*(\S+)\s*$", text)
        assert match is not None
        assert match.group(1) == name


def test_9router_entry_links_every_local_capability():
    text = (PROJECT_ROOT / "skills" / "9router" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for name in EXPECTED_9ROUTER_SKILLS - {"9router"}:
        assert f"/skills/{name}/SKILL.md" in text
    assert "raw.githubusercontent.com" not in text
