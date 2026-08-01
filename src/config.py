import os
from pathlib import Path

from dotenv import load_dotenv

from src.tool_environment import DEFAULT_TOOL_ENV_PASSTHROUGH

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")  # system config, models, and LLM_API_KEY
load_dotenv(_PROJECT_ROOT / ".env.secrets")  # skill-specific secrets; never overrides .env

# ---------------------------------------------------------------------------
# Ensure optional skill env vars always exist in os.environ.
# Some third-party libraries / code paths may access os.environ[key] directly
# (rather than os.getenv(key, default)), which raises KeyError when unset.
# Setting defaults here prevents that regardless of whether .env.secrets
# exists on disk.
# ---------------------------------------------------------------------------
_OPTIONAL_SKILL_ENV = DEFAULT_TOOL_ENV_PASSTHROUGH
for _key in _OPTIONAL_SKILL_ENV:
    os.environ.setdefault(_key, "")

# Required vars
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise ValueError("LLM_API_KEY must be set in .env")

# Agent models — rename from AGENT_MODEL for clarity.
# Backward compat: fall back to AGENT_MODEL if AGENT_MODEL_LOW is unset.
AGENT_MODEL_LOW = os.getenv("AGENT_MODEL_LOW") or os.getenv("AGENT_MODEL")
if not AGENT_MODEL_LOW:
    raise ValueError("AGENT_MODEL_LOW (or AGENT_MODEL) must be set in .env")
AGENT_MODEL_HIGH = os.getenv("AGENT_MODEL_HIGH") or AGENT_MODEL_LOW

# Optional with defaults
LLM_BASE_URL = os.getenv("LLM_BASE_URL")  # e.g. https://api.anthropic.com or custom proxy
AGENT_TEMPERATURE_LOW = float(os.getenv("AGENT_TEMPERATURE_LOW", os.getenv("AGENT_TEMPERATURE", "0.7")))
AGENT_TEMPERATURE_HIGH = float(os.getenv("AGENT_TEMPERATURE_HIGH", "0.3"))
SESSION_IDLE_TIMEOUT = int(os.getenv("SESSION_IDLE_TIMEOUT", "7200"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
EXECUTOR_PORT = int(os.getenv("EXECUTOR_PORT", "5001"))
if not 1 <= EXECUTOR_PORT <= 65535:
    raise ValueError("EXECUTOR_PORT must be between 1 and 65535")
EXECUTOR_HTTP_TIMEOUT_GRACE = float(os.getenv("EXECUTOR_HTTP_TIMEOUT_GRACE", "15"))
if EXECUTOR_HTTP_TIMEOUT_GRACE < 1:
    raise ValueError("EXECUTOR_HTTP_TIMEOUT_GRACE must be at least 1 second")
EXECUTOR_API_TOKEN = os.getenv("EXECUTOR_API_TOKEN", "").strip()
EXECUTOR_REQUIRE_AUTH = os.getenv("EXECUTOR_REQUIRE_AUTH", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
if EXECUTOR_REQUIRE_AUTH and not EXECUTOR_API_TOKEN:
    raise ValueError("EXECUTOR_API_TOKEN is required when EXECUTOR_REQUIRE_AUTH=1")

# WazzapAgents webhook is always-on (auto-restarts on crash). These
# tunables control how aggressively we retry delivery and verify the
# endpoint before submitting a task. See session_manager.py for usage.
WEBHOOK_RETRY_MAX = int(os.getenv("WEBHOOK_RETRY_MAX", "15"))
WEBHOOK_RETRY_BASE_BACKOFF = float(os.getenv("WEBHOOK_RETRY_BASE_BACKOFF", "1.0"))
WEBHOOK_RETRY_MAX_BACKOFF = float(os.getenv("WEBHOOK_RETRY_MAX_BACKOFF", "60.0"))
WEBHOOK_HEALTH_CHECK_ATTEMPTS = int(os.getenv("WEBHOOK_HEALTH_CHECK_ATTEMPTS", "5"))
WEBHOOK_HEALTH_CHECK_TIMEOUT = float(os.getenv("WEBHOOK_HEALTH_CHECK_TIMEOUT", "15.0"))

config = {
    "llm_api_key": LLM_API_KEY,
    "llm_base_url": LLM_BASE_URL,
    "agent_model_low": AGENT_MODEL_LOW,
    "agent_model_high": AGENT_MODEL_HIGH,
    "agent_temperature_low": AGENT_TEMPERATURE_LOW,
    "agent_temperature_high": AGENT_TEMPERATURE_HIGH,
    "session_idle_timeout": SESSION_IDLE_TIMEOUT,
    "log_level": LOG_LEVEL,
    "flask_port": FLASK_PORT,
    "executor_port": EXECUTOR_PORT,
    "executor_http_timeout_grace": EXECUTOR_HTTP_TIMEOUT_GRACE,
    "executor_api_token": EXECUTOR_API_TOKEN,
    "executor_require_auth": EXECUTOR_REQUIRE_AUTH,
    "webhook_retry_max": WEBHOOK_RETRY_MAX,
    "webhook_retry_base_backoff": WEBHOOK_RETRY_BASE_BACKOFF,
    "webhook_retry_max_backoff": WEBHOOK_RETRY_MAX_BACKOFF,
    "webhook_health_check_attempts": WEBHOOK_HEALTH_CHECK_ATTEMPTS,
    "webhook_health_check_timeout": WEBHOOK_HEALTH_CHECK_TIMEOUT,
}
