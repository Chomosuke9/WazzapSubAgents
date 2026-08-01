import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_environment_exposes_one_local_sandbox_port_without_mode_switches():
    config_template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert re.search(r"(?m)^EXECUTOR_PORT=5001$", config_template)
    assert "EXECUTOR_MANAGEMENT_MODE" not in config_template
    assert "CONTAINER_EXECUTOR_URL" not in config_template
    assert "SUBAGENT_HOST_STORAGE_DIR" not in config_template


def test_all_9router_settings_live_in_secret_template():
    config_template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    secret_template = (PROJECT_ROOT / ".env.secrets.example").read_text(
        encoding="utf-8"
    )

    assert "NINEROUTER_URL=" not in config_template
    assert re.search(r"(?m)^NINEROUTER_URL=", secret_template)
    assert re.search(r"(?m)^NINEROUTER_KEY=", secret_template)
