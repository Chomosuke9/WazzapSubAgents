# WazzapSubAgents — Architecture

WazzapSubAgents is a small **containerised executor service** that runs
autonomous agents ("sub-agents") in a sandboxed Docker container on behalf of a
parent orchestrator (typically the [WazzapAgents] bridge). A sub-agent is given
a free-form instruction plus some input files, and is free to run arbitrary
`bash`, `python`, or `javascript` code inside the sandbox until it decides the
task is done — at which point it calls `end_task(...)` with a report and a list
of deliverable files.

This document explains how the whole thing fits together so you can touch any
layer with confidence.

[WazzapAgents]: https://github.com/Chomosuke9/WazzapAgents

---

## 1. High-level topology

```
 ┌──────────────────────┐  HTTP POST /execute            ┌───────────────────────────────┐
 │ WazzapAgents bridge  ├───────────────────────────────▶│ executor-service  (Flask)     │
 │ (parent orchestrator)│  {session_id, instruction,     │                               │
 │                      │   input_files, callback_url,   │   src/app.py                  │
 │                      │   progress_webhook}            │   :5000                        │
 │                      │◀───────────────────────────────┤   │                            │
 └──────────────────────┘  progress / complete webhooks  │   │                            │
                                                         │   ▼                            │
                                                         │  ExecutorAgent (src/agent.py)  │
                                                         │  LLM ReAct loop                │
                                                         │  (LangChain ChatOpenAI)        │
                                                         │   │                            │
                                                         │   │  HTTP POST /bash /python   │
                                                         │   │  /javascript (per turn)    │
                                                         │   ▼                            │
                                                         │  executor-executor sidecar     │
                                                         │  src/executor_server.py :5001  │
                                                         │  (runs user code in workdir)   │
                                                         └───────────────────────────────┘
                       ▲                                          │
                       │                                          ▼
                       │                           ┌──────────────────────────────┐
                       │                           │ /storage (bind-mounted on    │
                       └───────────────────────────┤  both containers + host)     │
                                                   │  ── subagent_work/<sid>/     │
                                                   │     input/                   │
                                                   │     <agent-produced files>   │
                                                   └──────────────────────────────┘
```

There are **two containers** and they must agree on a **shared host path** that
both also share with the parent bridge.

### `executor-service` — main Flask API (`src/app.py`, port 5000)

- Receives `/execute` requests from WazzapAgents.
- Manages sessions, workdirs, and the FIFO queue.
- Runs the **LLM agent loop** (`src/agent.py`) in a background thread.
- Forwards every tool call the LLM makes to the executor sidecar over HTTP.
- Fires `progress` / `complete` webhooks back to the bridge.

### `executor-executor` — in-container executor sidecar (`src/executor_server.py`, port 5001)

- Pure dumb executor: receives `/bash`, `/python`, `/javascript` POSTs, runs the
  code with `cwd = <session workdir>`, returns `{stdout, stderr, returncode}`.
- Has the document-processing toolchain installed (see
  [Dockerfile](./Dockerfile): poppler-utils, tesseract, libreoffice, qpdf,
  ghostscript, reportlab, python-docx, python-pptx, openpyxl, pandas,
  pptxgenjs, docx, pdf-lib, …).
- Mounts `./skills/` **read-only** at `/skills/` so agents can read
  `SKILL.md` files at runtime.

This split is deliberate: the main service talks to the LLM and the parent
bridge, while the sidecar is the only thing that actually executes code. If the
LLM goes rogue, the blast radius is a single short-lived workdir inside the
sidecar.

---

## 2. Request lifecycle

The entry point is `POST /execute` on the main service (`src/app.py:36-82`):

1. **Validate** `session_id` + `instruction`. `session_id` is sanitised so it
   can't traverse outside `WORKDIR_BASE` when used as a directory name
   (`src/session_manager.py:56-70`, mirrored in `src/executor_server.py:25-46`).
2. **Get or create a session.** Each session gets:
   - a dedicated workdir at `${WORKDIR_BASE}/<session_id>/`;
   - a `Session` object tracking `last_activity`, `status`, `result`,
     `callback_url`, `progress_webhook`, `progress_logs`
     (`src/session_manager.py:15-25`).
3. **Stage input files.** Whatever paths the bridge passed in `input_files` are
   **copied** into `<workdir>/input/<basename>`
   (`src/input_staging.py`). This is the single fix for a whole class of
   cross-container "file not found" bugs: the sidecar only bind-mounts
   `${WORKDIR_BASE}`, so inputs staged outside it would be invisible.
4. **Enqueue / acquire a slot** in the global `SubAgentQueue`
   (`src/concurrency.py`). At most `SUBAGENT_GLOBAL_LIMIT` (default **1**)
   agents run concurrently; further sessions block in FIFO order. While
   waiting, the queue fires `queued` / `queue_advanced` events via the
   session's `progress_webhook`.
5. **Return `202 processing` immediately.** The agent loop runs in a daemon
   thread so the HTTP request doesn't have to stay open for the whole task.

When the agent loop finishes:

6. **Store the result** on the `Session` and fire a `complete` webhook to the
   bridge's `callback_url` (if any).
7. The result is also readable at `GET /sessions/<session_id>/result`.

Sessions that have been `completed` and idle for more than
`SESSION_IDLE_TIMEOUT` seconds (default 600) are cleaned up by a background
thread (`src/session_manager.py:183-194`) — the workdir is deleted with
`shutil.rmtree`.

---

## 3. Agent loop (ReAct with native tool calls)

`ExecutorAgent.execute` (`src/agent.py`) is a standard **ReAct** loop built on
LangChain's `ChatOpenAI.bind_tools(...)`. Four tools are exposed to the model:

| Tool         | Args                                      | What it does |
|--------------|-------------------------------------------|--------------|
| `bash`       | `reason`, `command`                       | `POST /bash` → sidecar runs `sh -c command` in workdir |
| `python`     | `reason`, `code`                          | `POST /python` → sidecar `exec`s Python in a stdout-capturing context |
| `javascript` | `reason`, `code`                          | `POST /javascript` → sidecar writes code to a tmp file and runs `node` |
| `end_task`   | `success`, `report`, `output_files?`      | Exits the loop with a final report + deliverable paths |

Each turn:

1. The main service calls the LLM with the running conversation.
2. The model must emit exactly one native `tool_call` (plain-text replies are
   counted and, after `AGENT_NO_TOOL_RETRY_MAX` attempts, the agent gives up).
3. `_dispatch_tool` runs the tool against the sidecar and appends the output
   back into the conversation as a `ToolMessage`.
4. A `progress` event (with the `reason`) is fired to the bridge so the end
   user can see what the agent is doing (`SessionManager.append_progress`).
5. Loop until the model calls `end_task`.

The loop also has guard-rails:

- **LLM retry with backoff** on rate-limits / 5xx / network errors
  (`_is_retryable_llm_error`, `_retry_after_seconds` honours `Retry-After`).
- **Stuck-loop detector** — if the agent fires the same tool call signature
  `AGENT_STUCK_LOOP_THRESHOLD` (default 5) times in a row, it is force-stopped.
- **Schema contract** — every tool requires a `reason` field so the progress
  webhook always has something human-readable to surface in WhatsApp.

The system prompt constructed by `_build_system_prompt`
(`src/agent.py:414-455`) tells the model:

- where `/skills/` lives and how to read it;
- that input files are already staged at the listed paths — don't search the
  filesystem;
- to write output anywhere in the workdir;
- to only list final **deliverable** files in `end_task(output_files=[...])` —
  not scratch or intermediate files.

When `end_task` fires, `_resolve_declared_output_files`
(`src/agent.py:350-412`) validates the declared paths: each must (a) exist as
a regular file and (b) live strictly inside the workdir. Anything else is
dropped with a logged warning.

---

## 4. File-sharing contract

Because there are three processes that need to agree on paths (bridge,
main service, sidecar), the file-sharing contract is the most important
thing to understand if you're deploying or debugging this stack.

### The shared-host-path rule

`WORKDIR_BASE` (default `/storage/subagent_work`) **must**:

1. Exist on the host.
2. Be bind-mounted at the **same path** into both `executor-service` and
   `executor-executor` — `/storage:/storage:rw` in `docker-compose.yml`.
3. Be readable/writable by the parent bridge, so it can stage `input_files`
   beforehand and read `output_files` afterwards.

If any of those is violated, the agent will report success but the bridge will
see "file not found" when it tries to deliver the outputs. See the commentary
at the top of [`docker-compose.yml`](./docker-compose.yml) for the contract.

### Per-session layout

```
${WORKDIR_BASE}/
└── <session_id>/            ← sanitised, can't traverse
    ├── input/               ← staged by input_staging.py
    │   ├── contract.pdf
    │   └── logo.png
    ├── report.pdf           ← agent-produced
    └── invoice.docx         ← agent-produced (declared in end_task)
```

- `<session_id>/input/` is populated by the **main service** before the agent
  starts; the sidecar only reads it.
- Anything else the agent writes lands in `<session_id>/` directly (that is
  the `cwd` the sidecar hands to `subprocess.run`). Use relative paths like
  `./report.pdf`.
- The agent declares which files are deliverables via
  `end_task(output_files=[...])`. Those paths are validated, deduped, and
  returned to the bridge as **absolute host paths** so the bridge can hand
  them to the WhatsApp media upload step.
- On session cleanup (idle timeout), the whole `<session_id>/` subtree is
  `rmtree`'d. **Do not rely on workdirs surviving past the session.**

### Absolute paths to avoid

These directories do **not** exist in the sidecar and will silently make
output invisible to the bridge — check your skill docs and prompts for them:

- `/output/` — legacy Anthropic-style path, leftover from upstream templates.
- `/mnt/user-data/outputs/` — also legacy; not mounted anywhere.
- `/tmp/` — exists but is not bind-mounted, so the bridge cannot read it.

Always write to the current working directory (`.`) or an explicit workdir
path.

---

## 5. Skill system

`./skills/` is a curated directory of **LLM-consumable reference
documentation** for common document-processing tasks. It is mounted **read-only**
into the sidecar at `/skills/` (see `src/docker_manager.py:103-114` for native
mode; the same mount is declared in `docker-compose.yml`).

The agent's system prompt explicitly tells the model:

> If you need help with specific file formats (DOCX, PDF, XLSX, PPTX, etc.),
> specialized documentation and code examples are available in `/skills/`. You
> can explore this directory using `bash` (e.g. `ls -R /skills/`) and read the
> `SKILL.md` files (e.g. `cat /skills/docx/SKILL.md`).

### Layout

```
skills/
├── canvas-design/           ← poster / art rendering
│   ├── SKILL.md
│   └── canvas-fonts/        ← TTF fonts loaded by reportlab/Pillow
├── docx/
│   └── SKILL.md             ← single big doc (Node.js docx + python-docx)
├── pdf/
│   ├── SKILL.md             ← entry point + quick decision tree
│   ├── creation.md          ← reportlab / pdf-lib
│   ├── editing.md           ← pypdf, qpdf, reportlab overlays
│   ├── extraction.md        ← pdfplumber, pypdf, OCR (tesseract)
│   └── transformation.md    ← merge / split / rotate / watermark
├── pptx/
│   ├── SKILL.md
│   ├── creation.md          ← pptxgenjs (Node.js)
│   ├── editing.md           ← python-pptx
│   └── extraction.md        ← python-pptx + markitdown
└── xlsx/
    └── SKILL.md             ← openpyxl + pandas
```

### Skill authoring rules

1. **Every snippet must be runnable as-is** inside the sidecar. The sidecar's
   cwd *is* the workdir; use relative paths (`./invoice.docx`). Never write
   `/output/...` or `/mnt/user-data/...`.
2. **Pick libraries we actually ship** (see Dockerfile). Don't reference
   PyMuPDF/fitz — we use pypdf.
3. **SKILL.md is the entry point**; split into sub-docs only when a skill is
   too large to fit in one LLM context window. The agent reads SKILL.md
   first.
4. **No Anthropic/Claude template leakage** — this project runs on
   OpenAI-compatible models via LangChain. Refer to "the agent", not "the
   next Claude".
5. **Declare only deliverables** — every skill's "Best Practices" section
   must remind the agent to exclude scratch files from
   `end_task(output_files=[...])`.

---

## 6. Concurrency, resilience, and webhooks

### Global FIFO gate

`SubAgentQueue` (`src/concurrency.py`) is a `threading.Condition`-backed
FIFO queue that caps concurrent agent executions to `SUBAGENT_GLOBAL_LIMIT`
(default **1**). Keeping it at 1 means:

- Only one LLM call-chain is in flight at a time — cheap and predictable
  cost-wise.
- Only one sidecar code execution at a time — the `_PY_EXEC_LOCK`
  already serialises Python stdout/stderr hijacking anyway.

While queued, the session receives `queued` and `queue_advanced` webhook
events so the bridge can tell the user "you're #3 in line".

### Webhook reliability

`SessionManager._fire_webhook` retries with exponential backoff up to
`WEBHOOK_RETRY_MAX` (default 5) times, capped at `WEBHOOK_RETRY_MAX_BACKOFF`
seconds. All webhooks are fired on a daemon thread so the agent loop never
blocks on the bridge.

### LLM resilience

Tunables (all env-overridable):

- `AGENT_LLM_RETRY_MAX=5` — retries on 429 / 5xx / timeout / connection.
- `AGENT_LLM_RETRY_BASE_BACKOFF=2.0`, `AGENT_LLM_RETRY_MAX_BACKOFF=60.0`.
- `AGENT_STUCK_LOOP_THRESHOLD=5` — max repeated identical tool calls before
  aborting.
- `AGENT_NO_TOOL_RETRY_MAX=3` — max plain-text replies before aborting.

### Session cleanup

Completed sessions older than `SESSION_IDLE_TIMEOUT` (default 600 s) are
deleted every 10 s by a daemon thread. The workdir is `rmtree`'d on cleanup —
**outputs must be collected by the bridge before then** (the `complete`
webhook is fired as soon as the result is stored, so this is a
non-issue in practice).

---

## 7. Deployment modes

Two supported layouts, both live in this repo:

### A. Native (host runs main service, Docker only for the sidecar)

- `python main.py` on the host.
- `DockerManager` builds `executor-service:v1.0.0` from the `Dockerfile`,
  spawns one container named `executor-executor`, and bind-mounts
  `${WORKDIR_BASE}`, `./skills`, `./src`, `./main.py` into it.
- Main service talks to the sidecar over `localhost:5001`.
- Simpler to debug; good for local development.

### B. Compose (both main service and sidecar run in containers)

- `docker compose up` using [`docker-compose.yml`](./docker-compose.yml).
- Two services (`executor-service`, `executor-executor`) share a user-defined
  bridge network `executor-net`; the main service dials the sidecar at
  `http://executor-executor:5001` via the `CONTAINER_EXECUTOR_URL` env var.
- `/storage` is the shared mount with the bridge.
- Production-like; matches what WazzapAgents expects.

Regardless of mode, the **parent bridge (WazzapAgents) must share the same
`/storage` (or whatever `SUBAGENT_STORAGE_DIR` is) with both containers** so
input/output files actually cross the boundary.

---

## 8. Environment variables (cheat sheet)

| Variable                      | Default                        | Purpose |
|-------------------------------|--------------------------------|---------|
| `LLM_API_KEY`                 | **required**                   | API key for the OpenAI-compatible endpoint |
| `AGENT_MODEL`                 | **required**                   | Model identifier (e.g. `gpt-4o-mini`, or whatever the proxy exposes) |
| `LLM_BASE_URL`                | unset (→ OpenAI default)       | Custom OpenAI-compatible endpoint |
| `AGENT_TEMPERATURE`           | `0.7`                          | LLM sampling temperature |
| `FLASK_PORT`                  | `5000` (main) / `5001` (sidecar) | HTTP listen port |
| `CONTAINER_EXECUTOR_URL`      | `http://localhost:5001`        | Main service → sidecar URL |
| `WORKDIR_BASE`                | `/storage/subagent_work`       | Per-session workdir root (must be shared-mounted) |
| `SUBAGENT_STORAGE_DIR`        | `/storage`                     | Host path of the `/storage` bind mount |
| `SESSION_IDLE_TIMEOUT`        | `600`                          | Seconds before a completed session's workdir is deleted |
| `SUBAGENT_GLOBAL_LIMIT`       | `1`                            | Max concurrent agent executions |
| `AGENT_LLM_RETRY_MAX`         | `5`                            | LLM call retry budget |
| `AGENT_STUCK_LOOP_THRESHOLD`  | `5`                            | Max identical tool calls before aborting |
| `AGENT_NO_TOOL_RETRY_MAX`     | `3`                            | Max plain-text replies before aborting |
| `WEBHOOK_RETRY_MAX`           | `5`                            | Webhook delivery retry budget |
| `LOG_LEVEL`                   | `INFO`                         | Python logging level |

---

## 9. Where to look when something breaks

| Symptom                                         | Likely file / module |
|-------------------------------------------------|----------------------|
| `/execute` returns 400                          | `src/app.py` → `SessionManager.get_or_create` path validation |
| Agent reports "file not found" on input         | Did the bridge write into a path under `SUBAGENT_STORAGE_DIR`? Check `src/input_staging.py` |
| Agent runs forever, no progress                 | `SubAgentQueue` — session is waiting; check `src/concurrency.py` and the bridge's `progress_webhook` |
| Model replies with plain text, no tool call     | `src/agent.py` `_run_loop` → `NO_TOOL_RETRY_MAX` |
| Output files missing after `end_task`           | `_resolve_declared_output_files` dropped them (not a file / outside workdir) — check `session_id`-tagged logs |
| Sidecar container unreachable                   | `DockerManager.start_container` / `docker compose logs executor-executor` |
| Agent doesn't use a skill you added             | Did you mount `./skills:/skills:ro`? Is the `SKILL.md` at the top level of the subdir? |

[WazzapAgents]: https://github.com/Chomosuke9/WazzapAgents
