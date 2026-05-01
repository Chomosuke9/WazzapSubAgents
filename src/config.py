import os
from dotenv import load_dotenv

load_dotenv()

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
SESSION_IDLE_TIMEOUT = int(os.getenv("SESSION_IDLE_TIMEOUT", "600"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
CONTAINER_EXECUTOR_URL = os.getenv("CONTAINER_EXECUTOR_URL", "http://localhost:5001")

# WazzapAgents webhook is always-on (auto-restarts on crash). These
# tunables control how aggressively we retry delivery and verify the
# endpoint before submitting a task. See session_manager.py for usage.
WEBHOOK_RETRY_MAX = int(os.getenv("WEBHOOK_RETRY_MAX", "10"))
WEBHOOK_RETRY_BASE_BACKOFF = float(os.getenv("WEBHOOK_RETRY_BASE_BACKOFF", "0.5"))
WEBHOOK_RETRY_MAX_BACKOFF = float(os.getenv("WEBHOOK_RETRY_MAX_BACKOFF", "30.0"))
WEBHOOK_HEALTH_CHECK_ATTEMPTS = int(os.getenv("WEBHOOK_HEALTH_CHECK_ATTEMPTS", "3"))
WEBHOOK_HEALTH_CHECK_TIMEOUT = float(os.getenv("WEBHOOK_HEALTH_CHECK_TIMEOUT", "5.0"))

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
    "container_executor_url": CONTAINER_EXECUTOR_URL,
    "webhook_retry_max": WEBHOOK_RETRY_MAX,
    "webhook_retry_base_backoff": WEBHOOK_RETRY_BASE_BACKOFF,
    "webhook_retry_max_backoff": WEBHOOK_RETRY_MAX_BACKOFF,
    "webhook_health_check_attempts": WEBHOOK_HEALTH_CHECK_ATTEMPTS,
    "webhook_health_check_timeout": WEBHOOK_HEALTH_CHECK_TIMEOUT,
}
