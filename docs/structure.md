# Project Structure

## Directory tree

```
prueba/
├── .gitignore
├── MCP/                            # MCP server — runs inside Docker
│   ├── app/
│   │   ├── __init__.py             # gitignored (docstring only, not versioned)
│   │   ├── config.py               # environment variables (HOST, PORT, DATASET_BASE_URL, LOG_LEVEL)
│   │   ├── dataset.py              # HTTP client, metadata cache, dataset downloads
│   │   ├── logging_config.py       # centralized logging configuration
│   │   └── server.py               # FastMCP instance, lifespan, 3 tool definitions
│   ├── .dockerignore
│   ├── .env.example                # template for MCP environment variables
│   ├── Dockerfile
│   ├── docker-compose.yml          # mcp service + optional ngrok tunnel service
│   ├── requirements.txt            # mcp[cli], httpx
│   └── task_mcp.md                 # original task specification (not user docs)
│
└── managed_agents/                 # orchestrator — runs locally as a Python process
    ├── templates/
    │   └── index.html              # single-page chat UI (served by web_app.py)
    ├── .agent_config.json          # gitignored; persists agent_id + environment_id
    ├── .env.example                # template for ANTHROPIC_API_KEY and MCP_URL
    ├── .venv/                      # gitignored virtualenv
    ├── inspect_session.py          # CLI utility to inspect a session by ID
    ├── orchestrator.py             # agent/environment lifecycle + CLI entry point
    ├── requirements.txt            # anthropic, python-dotenv, flask
    ├── system_prompt.txt           # agent system prompt (data policy rules)
    ├── task_managed_agents.md      # original task specification (not user docs)
    └── web_app.py                  # Flask backend for the web chat UI
```

## Module responsibilities

### `MCP/app/config.py`

Reads four environment variables (`HOST`, `PORT`, `DATASET_BASE_URL`, `LOG_LEVEL`) with sensible defaults. No secrets — the dataset is public. This module is imported by `dataset.py` and `server.py`; it should not import from either.

### `MCP/app/dataset.py`

Single responsibility: access the public dataset. Owns:
- The global `httpx.AsyncClient` singleton (lazy creation, reused across requests)
- The in-memory `METADATA` dict (slug -> series info, populated once at startup)
- `load_metadata()`: idempotent download and parse of `metadata.json`
- `fetch_latest()`: download and parse `latest.json`
- `fetch_csv(categoria, slug)`: download a CSV file from `data/{categoria}/{slug}.csv`

All external errors are caught here and re-raised as `DatasetError` with safe, user-facing messages. Internal detail goes only to the log.

### `MCP/app/server.py`

Owns the FastMCP application instance and all three tool definitions. Wires together `config`, `dataset`, and `logging_config`. The `lifespan` context manager triggers `load_metadata()` at startup. Each tool function handles its own input validation and delegates data access to `dataset`.

Tools must not be added here without a corresponding entry in `dataset.py` for any new data access pattern. Business logic (filtering, sorting, date parsing) lives in the tool functions, not in `dataset.py`.

### `MCP/app/logging_config.py`

Configures a single root logger (`app`) with a `StreamHandler` to stdout. All module loggers are children (`app.server`, `app.dataset`). The handler format includes timestamp, level, logger name, and message. Does not propagate to the global root logger to avoid duplicate output with uvicorn/starlette.

### `managed_agents/orchestrator.py`

Entry point for the CLI. Manages the full agent lifecycle: reads config from `.agent_config.json`, creates agent and environment if missing, persists new IDs, creates a session, and runs the stream event loop. Exports functions (`get_or_create_resources`, `require_env`, `read_system_prompt`, `run_turn`, `CONSOLE_URL`) consumed by `web_app.py`.

### `managed_agents/web_app.py`

Flask application. Shares the orchestrator's agent/environment setup (imported at module level). Each `POST /api/session` creates a new Managed Agent session. Each `POST /api/chat` opens the agent stream and re-emits events as SSE. The `ANTHROPIC_API_KEY` never leaves the server process.

### `managed_agents/inspect_session.py`

Standalone debugging utility. Takes a session ID as a command-line argument, retrieves the session status and full event list from the API, and prints a human-readable transcript. Not part of the main application flow; use it when you need to inspect what happened in a session without access to the Anthropic Console.

### `managed_agents/system_prompt.txt`

The agent's system prompt. Defines behavioral rules: data-only answers, no financial advice, mandatory ambiguity resolution for multi-series queries, always include unit and date. Changes here require recreating the agent (`--reset`) because the prompt is embedded in the agent object at creation time.

### `managed_agents/templates/index.html`

Self-contained single-page application. Pure HTML/CSS/JS — no build step, no dependencies. Communicates with `web_app.py` via `fetch` (JSON for session creation, ReadableStream for SSE chat). Renders agent text and tool chips in real time as SSE events arrive.

## What goes where

| Concern | Location |
|---------|----------|
| Dataset access and caching | `MCP/app/dataset.py` only |
| MCP tool definitions | `MCP/app/server.py` only |
| Server configuration | `MCP/app/config.py` (env vars) + `MCP/.env` (values) |
| Agent/environment lifecycle | `managed_agents/orchestrator.py` |
| Web API for the browser | `managed_agents/web_app.py` |
| Agent behavioral rules | `managed_agents/system_prompt.txt` |
| Persisted agent/env IDs | `managed_agents/.agent_config.json` (gitignored) |

Do not put dataset-fetching logic in `server.py`. Do not put MCP tool definitions in `dataset.py`. Do not hard-code credentials or API keys in any source file — use `.env` loaded by `python-dotenv` or Docker env files.
