# Executor Service

Standalone helper service that manages Docker containers, agent execution, and endpoints for WazzapAgents.

## Quick Start

### 1. Environment

Copy the template and fill in your LLM API key:

```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY and AGENT_MODEL
```

### 2. Run

**Option A: Native Python**

```bash
pip install -r requirements.txt
python main.py
```

**Option B: Docker Build + Run**

```bash
docker build -t executor-service:v1.0.0 .
docker run -d \
  -p 5000:5000 \
  -p 5001:5001 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /storage:/storage:ro \
  --env-file .env \
  executor-service:v1.0.0
```

**Option C: Docker Compose**

```bash
docker-compose up -d
```

On startup the service will:
1. Check if `executor-service:v1.0.0` Docker image exists (build if missing when running native)
2. Start the in-container executor sidecar on `:5001`
3. Start the main Flask service on `:5000`

---

## API Contract

### POST /execute

Submit a task to the agent.

**Request:**

```json
{
  "session_id": "user_123_task_abc",
  "instruction": "Extract all tables from /storage/doc.pdf and save each as CSV in /tmp/work_user_123_task_abc/",
  "input_files": [
    "/storage/doc.pdf",
    "/storage/config.json"
  ]
}
```

**Notes:**
- `session_id` — unique identifier for this task
- `instruction` — natural language instruction (agent decides how to approach)
- `input_files` — **absolute paths on the host filesystem** (not uploaded, agent reads directly)

**Immediate Response: `202 Accepted`**

```json
{
  "status": "processing",
  "session_id": "user_123_task_abc",
  "message": "Agent starting..."
}
```

---

### GET /sessions/<session_id>/result

Poll for the final result.

**Success Response (`200`)**

```json
{
  "session_id": "user_123_task_abc",
  "success": true,
  "report": "Extracted 3 tables from PDF. Files saved to /tmp/work_user_123_task_abc/",
  "output_files": [
    "/tmp/work_user_123_task_abc/table1.csv",
    "/tmp/work_user_123_task_abc/table2.csv",
    "/tmp/work_user_123_task_abc/table3.csv"
  ],
  "processing_time_sec": 42.5
}
```

**Error Response (`404`) — result not found or expired**

```json
{
  "success": false,
  "report": "Result not found or expired"
}
```

**Important:** Results are **ephemeral** (in-memory only). They are lost when:
- Session idle timeout expires (default: 600s)
- Service/container is restarted
- WazzapAgents must poll before timeout

---

### GET /health

```json
{
  "status": "ok"
}
```

---

## Integration from WazzapAgents

```python
import requests
import time

# 1. Submit task
resp = requests.post("http://localhost:5000/execute", json={
    "session_id": "task_123",
    "instruction": "Extract tables from /storage/doc.pdf and save as CSV",
    "input_files": ["/storage/doc.pdf"]
})
resp.raise_for_status()
data = resp.json()
session_id = data["session_id"]

# 2. Poll for result
for _ in range(60):  # max 60 attempts
    time.sleep(5)
    result = requests.get(f"http://localhost:5000/sessions/{session_id}/result")
    if result.status_code == 200:
        print(result.json())
        break
else:
    print("Timeout polling result")
```

---

## Session Lifecycle

```
POST /execute
    |
    v
Session created  -->  Agent loop runs (bash/python tools)
    |                       |
    |                       v
    |               end_task called
    |                       |
    |                       v
    |               Result stored in-memory
    |                       |
    |<----------------------+
    |
GET /sessions/<id>/result  <--  WazzapAgents polls
    |
    v
Idle timeout reached  -->  Result deleted + workdir cleaned
```

- Container stays running (long-lived)
- Only session result & workdir are ephemeral

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_API_KEY` | Yes | — | LLM API key (e.g. Anthropic, OpenAI) |
| `AGENT_MODEL` | Yes | — | Model name (e.g. `claude-3-5-sonnet`) |
| `AGENT_TEMPERATURE` | No | 0.7 | Sampling temperature |
| `FLASK_PORT` | No | 5000 | Main service port |
| `CONTAINER_EXECUTOR_URL` | No | `http://localhost:5001` | In-container executor URL |
| `SESSION_IDLE_TIMEOUT` | No | 600 | Session result idle timeout (seconds) |
| `LOG_LEVEL` | No | INFO | Logging level |
| `WORKDIR_BASE` | No | `/tmp/work` (native) / `/storage/subagent_work` (compose) | Base directory for per-session workdirs. Must be on a filesystem the bridge can read so it can pick up `output_files`. |
| `SUBAGENT_STORAGE_DIR` | No | `/storage` | Host directory bind-mounted to `/storage` inside both containers. Used as the cross-process exchange for input/output files. |
| `SUBAGENT_WORKDIR_BASE` | No | `/storage/subagent_work` | docker-compose-only override of `WORKDIR_BASE` keeping it inside the shared mount. |

---

## File Sharing Contract (cross-process)

WazzapAgents passes **absolute file paths** in `input_files` and reads back
**absolute file paths** from `output_files`. Both processes therefore need
to agree on a directory that exists on the host *and* is mounted inside
this service's containers — otherwise:

- `input_files` paths handed to the agent will be missing inside the
  executor sidecar (bash/python can't read them), or
- `output_files` paths returned to the bridge will not exist on its side
  (it can't stage them as WhatsApp media).

The default contract used by `docker-compose.yml`:

| Concern | Host path | Container path |
|---------|-----------|----------------|
| Input staging by WazzapAgents | `/storage/subagent_in/<session_id>/` | same |
| Per-session workdir / outputs | `/storage/subagent_work/<session_id>/` | same |

The directories are unified under `/storage` (override via
`SUBAGENT_STORAGE_DIR` on the host side and the matching env on the
WazzapAgents side). The `executor-service` and `executor-executor`
containers both bind-mount the same host directory so paths are
identical inside and out, and `host.docker.internal` is wired in via
`extra_hosts` so the agent can POST `complete`/`progress` callbacks to
the bridge running on the host.

---

## Testing

```bash
# Unit tests (no docker required)
bash scripts/test_locally.sh

# Integration tests (requires docker daemon)
export RUN_INTEGRATION_TESTS=1
bash scripts/test_integration.sh
```

---

## Troubleshooting

### "Docker daemon not available"
- Service hard-exits if `/var/run/docker.sock` is not accessible
- Fix: mount docker socket when running container, or run natively with docker installed

### "Docker build failed"
- Check Dockerfile exists in working directory
- Check disk space

### "Result not found or expired"
- WazzapAgents did not poll fast enough
- Session idle timeout expired
- Fix: increase `SESSION_IDLE_TIMEOUT` or poll more frequently

### Agent returns error / max iterations
- LLM API key invalid or rate-limited
- Instruction too ambiguous for agent to decide tool calls
- Fix: check logs, provide clearer instruction

---

## Architecture

- `main.py` — Entry point (docker check → build → container start → Flask)
- `src/docker_manager.py` — Docker image and container lifecycle
- `src/session_manager.py` — Ephemeral session tracking & cleanup
- `src/agent.py` — LangChain agent loop with bash/python/end_task tools
- `src/container_client.py` — HTTP client to in-container executor
- `src/executor_server.py` — In-container Flask server for bash/python execution
- `src/app.py` — Main Flask app exposing `/execute`, `/health`, `/sessions/.../result`
- `src/config.py` — Environment variable loading & validation
- `src/logger.py` — Structured JSON logging to stdout

## Logging

All logs are structured JSON to stdout:

```json
{"timestamp": "2025-04-24T12:34:56Z", "level": "INFO", "message": "Session xyz started", "session_id": "xyz"}
```

Use `LOG_LEVEL=DEBUG` for verbose tool call logging.
