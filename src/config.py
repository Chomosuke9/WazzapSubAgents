import os
from dotenv import load_dotenv

load_dotenv()

# Required vars
LLM_API_KEY = os.getenv("LLM_API_KEY")
AGENT_MODEL = os.getenv("AGENT_MODEL")
if not LLM_API_KEY:
    raise ValueError("LLM_API_KEY must be set in .env")
if not AGENT_MODEL:
    raise ValueError("AGENT_MODEL must be set in .env")

# Optional with defaults
LLM_BASE_URL = os.getenv("LLM_BASE_URL")  # e.g. https://api.anthropic.com or custom proxy
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
SESSION_IDLE_TIMEOUT = int(os.getenv("SESSION_IDLE_TIMEOUT", "600"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
CONTAINER_EXECUTOR_URL = os.getenv("CONTAINER_EXECUTOR_URL", "http://localhost:5001")

config = {
    "llm_api_key": LLM_API_KEY,
    "llm_base_url": LLM_BASE_URL,
    "agent_model": AGENT_MODEL,
    "agent_temperature": AGENT_TEMPERATURE,
    "session_idle_timeout": SESSION_IDLE_TIMEOUT,
    "log_level": LOG_LEVEL,
    "flask_port": FLASK_PORT,
    "container_executor_url": CONTAINER_EXECUTOR_URL,
}
