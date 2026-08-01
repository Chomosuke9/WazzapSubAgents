from src import secrets_redaction


def test_configured_skill_keys_are_redacted_without_env_files(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_redaction, "_find_project_root", lambda: tmp_path)
    monkeypatch.setenv(
        "EXECUTOR_TOOL_ENV_PASSTHROUGH",
        "BRAVE_SEARCH_API_KEY,NINEROUTER_URL,NINEROUTER_KEY,CUSTOM_SKILL_TOKEN",
    )
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-secret-value")
    monkeypatch.setenv("NINEROUTER_KEY", "nine-secret-value")
    monkeypatch.setenv("NINEROUTER_URL", "https://router.example.test")
    monkeypatch.setenv("CUSTOM_SKILL_TOKEN", "custom-secret-value")
    secrets_redaction.rebuild()

    value = secrets_redaction.redact_secrets(
        "brave-secret-value nine-secret-value custom-secret-value "
        "https://router.example.test"
    )

    assert value == "[REDACTED] [REDACTED] [REDACTED] [REDACTED]"
    secrets_redaction._pattern = None


def test_placeholder_values_are_not_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_redaction, "_find_project_root", lambda: tmp_path)
    monkeypatch.setenv("EXECUTOR_TOOL_ENV_PASSTHROUGH", "NINEROUTER_KEY")
    monkeypatch.setenv("NINEROUTER_KEY", "sk-...")
    secrets_redaction.rebuild()

    assert secrets_redaction.redact_secrets("configure sk-... here") == "configure sk-... here"
    secrets_redaction._pattern = None
