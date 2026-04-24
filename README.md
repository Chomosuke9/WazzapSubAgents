# Executor Service

Standalone helper service that manages Docker containers, agent execution, and endpoints for WazzapAgents.

## Quick Start

1. Copy environment template and fill in your Anthropic API key:
   ```bash
   cp .env.example .env
   # Edit .env and set ANTHROPIC_API_KEY
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the service:
   ```bash
   python main.py
   ```

The service will:
- Check if `executor-service:v1.0.0` Docker image exists (build if missing)
- Start the in-container executor
- Start Flask on `:5000`

## API

### POST /execute
```json
{
  "session_id": "task_123",
  "instruction": "Extract tables from PDF and save as CSV",
  "input_files": ["/storage/doc.pdf"]
}
```

Response: `202 Accepted`
```json
{
  "status": "processing",
  "session_id": "task_123",
  "message": "Agent starting..."
}
```

### GET /sessions/<session_id>/result
Returns the final result once processing completes.

### GET /health
Returns `{"status": "ok"}`

## Docker Compose (Optional)

```bash
docker-compose up -d
```

## Testing

```bash
# Unit tests
bash scripts/test_locally.sh

# Integration tests (requires docker)
bash scripts/test_integration.sh
```

## Architecture

- `main.py` — Entry point (docker check → build → container start → Flask)
- `src/docker_manager.py` — Docker image and container lifecycle
- `src/session_manager.py` — Ephemeral session tracking
- `src/agent.py` — LangChain agent loop with bash/python/end_task tools
- `src/container_client.py` — HTTP client to in-container executor
- `src/executor_server.py` — In-container Flask server for bash/python execution
- `src/app.py` — Main Flask app exposing `/execute`

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| ANTHROPIC_API_KEY | Yes | — | Claude API key |
| AGENT_MODEL | Yes | — | Model name (e.g. claude-3-5-sonnet) |
| AGENT_TEMPERATURE | No | 0.7 | Sampling temperature |
| AGENT_MAX_TOKENS | No | 4096 | Max tokens per response |
| FLASK_PORT | No | 5000 | Main service port |
| CONTAINER_EXECUTOR_URL | No | http://localhost:5001 | In-container executor URL |
| CONTAINER_IDLE_TIMEOUT | No | 600 | Session idle timeout (seconds) |
| LOG_LEVEL | No | INFO | Logging level |
