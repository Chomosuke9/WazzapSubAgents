from src.tool_environment import (
    DEFAULT_TOOL_ENV_PASSTHROUGH,
    parse_tool_env_passthrough,
)


def test_default_tool_environment_contains_9router_and_brave():
    assert DEFAULT_TOOL_ENV_PASSTHROUGH == (
        "BRAVE_SEARCH_API_KEY",
        "NINEROUTER_URL",
        "NINEROUTER_KEY",
    )


def test_passthrough_is_stable_validated_and_deduplicated():
    assert parse_tool_env_passthrough(
        " CUSTOM_KEY,BRAVE_SEARCH_API_KEY,CUSTOM_KEY,bad-name,9BAD, "
    ) == ("CUSTOM_KEY", "BRAVE_SEARCH_API_KEY")


def test_passthrough_rejects_credentials_and_control_vars_case_insensitively():
    assert parse_tool_env_passthrough(
        "llm_api_key,SubAgent_Api_Token,EXECUTOR_BIND_HOST,"
        "executor_require_uid_isolation,WORKDIR_BASE,SAFE_SKILL_KEY"
    ) == ("SAFE_SKILL_KEY",)
