import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_compose_does_not_override_secret_env_file_with_empty_values():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert re.search(r"(?m)^\s+- \.env\.secrets\s*$", compose)
    assert not re.search(r"(?m)^\s+BRAVE_SEARCH_API_KEY:\s*", compose)
    assert not re.search(r"(?m)^\s+NINEROUTER_KEY:\s*", compose)
    assert "EXECUTOR_TOOL_ENV_PASSTHROUGH:" in compose


def test_9router_url_is_config_but_only_key_is_secret():
    config_template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    secret_template = (PROJECT_ROOT / ".env.secrets.example").read_text(
        encoding="utf-8"
    )

    assert re.search(r"(?m)^NINEROUTER_URL=", config_template)
    assert "NINEROUTER_URL=" not in secret_template
    assert re.search(r"(?m)^NINEROUTER_KEY=", secret_template)
