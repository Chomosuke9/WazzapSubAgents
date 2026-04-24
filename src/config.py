import os
from dotenv import load_dotenv

load_dotenv()

# Required vars
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
AGENT_MODEL = os.getenv("AGENT_MODEL")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY must be set in .env")
if not AGENT_MODEL:
    raise ValueError("AGENT_MODEL must be set in .env")

# Optional with defaults
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "4096"))
CONTAINER_IDLE_TIMEOUT = int(os.getenv("CONTAINER_IDLE_TIMEOUT", "600"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
CONTAINER_EXECUTOR_URL = os.getenv("CONTAINER_EXECUTOR_URL", "http://localhost:5001")

config = {
    "anthropic_api_key": ANTHROPIC_API_KEY,
    "agent_model": AGENT_MODEL,
    "agent_temperature": AGENT_TEMPERATURE,
    "agent_max_tokens": AGENT_MAX_TOKENS,
    "container_idle_timeout": CONTAINER_IDLE_TIMEOUT,
    "log_level": LOG_LEVEL,
    "flask_port": FLASK_PORT,
    "container_executor_url": CONTAINER_EXECUTOR_URL,
}
