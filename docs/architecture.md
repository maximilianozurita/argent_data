# Architecture

## Overview

The system is built from two independently deployed components that communicate over HTTP. Neither component is aware of the other's internal implementation — they are coupled only through the MCP protocol at a URL boundary.

```
User
 │
 ├─► CLI / web browser
 │        │
 │        ▼
 │   managed_agents/ (local Python process or Flask server)
 │        │  Anthropic Managed Agents API (HTTPS)
 │        ▼
 │   Claude agent (Anthropic cloud, sandboxed environment)
 │        │  MCP streamable-http (HTTPS via ngrok tunnel)
 │        ▼
 │   MCP/ (Docker container, local or remote)
 │        │  HTTP GET (raw.githubusercontent.com)
 │        ▼
 │   Public dataset (GitHub raw files)
```

## Component 1: MCP Server (`MCP/`)

**Role:** a stateless HTTP service that exposes Argentine economic data as three MCP tools. It has no database; all data comes from a public GitHub repository fetched on demand.

### Startup behavior

At startup (`lifespan` context manager in `server.py`), the server downloads `metadata.json` once and builds an in-memory map `slug -> {categoria, nombre, unidad, frecuencia, descripcion}`. This map is never refreshed during the server's lifetime. All subsequent tool calls that need series metadata read from this in-memory structure without any I/O.

### Tools

| Tool | I/O | Download per call |
|------|-----|-------------------|
| `list_series()` | reads in-memory metadata | none |
| `get_latest_value(slug)` | downloads `latest.json` | yes |
| `get_series_data(slug, desde, hasta)` | downloads `data/{categoria}/{slug}.csv` | yes |

### HTTP client strategy

A single `httpx.AsyncClient` instance (`_client` in `dataset.py`) is created lazily on the first tool call and reused for the lifetime of the process. Because the server runs in stateless HTTP mode (`stateless_http=True`), the lifespan may execute per-request in some deployment configurations. The `load_metadata()` function is idempotent — it exits early if `METADATA` is already populated — preventing redundant downloads.

`metadata.json` uses its own short-lived client (via `async with _new_client()`) so it can be called from `asyncio.run()` at startup without coupling to the global client's event loop.

### Transport

The server uses **streamable-http** transport (the current HTTP transport in the MCP Python SDK), not the older SSE-based transport. This means the endpoint is `/mcp`, not `/sse`. Agents connecting via URL must use the `/mcp` path.

### Error handling

All network and HTTP errors in `dataset.py` are caught and re-raised as `DatasetError` with a user-safe message. The actual error detail (status code, URL, exception type) is logged to stdout but never forwarded to the agent. Tool validation errors use `ToolError` from FastMCP, which produces structured MCP error responses rather than crashes.

### Containerization

The Docker image uses `python:3.12-slim`, runs as a non-root user (`appuser`, uid 1000), and sets `PYTHONUNBUFFERED=1` so logs appear immediately in `docker compose logs`. The `docker-compose.yml` defines two services: `mcp` (always) and `ngrok` (only with `--profile tunnel`).

## Component 2: Managed Agents Orchestrator (`managed_agents/`)

**Role:** a client-side program that manages the lifecycle of an Anthropic Managed Agent and routes user questions to it.

### Agent lifecycle

The Anthropic Managed Agents API has three persistent resources: **agent**, **environment**, and **session**.

- **Agent**: holds the model, system prompt, and MCP server URL. Created once and reused indefinitely via `.agent_config.json`.
- **Environment**: a sandboxed cloud execution context with network policy. Created once alongside the agent. Uses `limited` networking with `allow_mcp_servers: true`, which restricts all egress except to the MCP server registered on the agent.
- **Session**: ephemeral per-conversation context. Created fresh for each invocation (CLI) or each "New conversation" click (web UI).

The "create once, reuse by ID" pattern avoids redundant API calls and keeps agent configuration stable across runs. `--reset` deletes `.agent_config.json` and forces recreation, which is required when changing the model or system prompt.

### Stream-first event loop

The orchestrator opens the event stream **before** sending the user message — this is mandatory to avoid missing early events. It then sends the message and processes events synchronously:

- `agent.message` → streams text to the user
- `agent.mcp_tool_use` → prints `[MCP tool: <name>]` for visibility
- `session.status_idle` with `stop_reason.type == "requires_action"` → automatically sends `user.tool_confirmation` with `result: "allow"` for all pending tool IDs (the MCP is read-only, so no confirmation gate is needed)
- `session.status_terminated` / `session.error` → terminates the loop

### System prompt policy

The system prompt (`system_prompt.txt`) enforces hard constraints on the agent:

- **Data-only**: the agent must use exclusively MCP tool results. It cannot draw on its training knowledge for economic figures.
- **No financial advice**: it reports data neutrally, never recommending actions.
- **Ambiguity resolution**: for queries like "the dollar" (which maps to multiple series), the agent must call `list_series` first, identify all matching series, and ask the user to disambiguate before returning any value. This is specified as a deterministic rule.
- **Transparent calculations**: for comparative queries, the agent must fetch data via `get_series_data`, show the raw values and dates, and explain the formula.

### Web frontend

`web_app.py` is a Flask server that wraps the same orchestrator logic and exposes two endpoints consumed by a single-page HTML chat UI:

- `POST /api/session` creates a new Managed Agent session and returns its ID and a Anthropic Console URL.
- `POST /api/chat` accepts `{session_id, message}`, opens the agent stream, and re-emits events as Server-Sent Events (SSE) with types `text`, `tool`, `error`, and `done`.

The Flask server holds the `ANTHROPIC_API_KEY` server-side; the browser never sees it. The agent and environment resources are shared across all web conversations (reused from `.agent_config.json`); only the session is per-conversation.

## Data flow for a typical query

1. User sends "What is the blue dollar today?" via CLI or web UI.
2. Orchestrator creates a session (or reuses the web session) and sends the message.
3. The Claude agent receives the message in its sandboxed environment. Its MCP toolset is registered with `arg-data` as the server name.
4. The agent calls `list_series()` (if it needs to disambiguate) or directly calls `get_latest_value("dolar_blue_venta")`.
5. The Anthropic cloud infrastructure makes an HTTP request to the MCP server at the configured `MCP_URL` using the streamable-http transport.
6. The MCP server's `get_latest_value` tool downloads `latest.json` from the public dataset, finds the matching slug, and returns `{slug, nombre, valor, unidad, fecha}`.
7. The agent composes a response citing the value, unit, and date, following the system prompt constraints.
8. The orchestrator streams the response text back to the user.

## Key architectural constraints

- **The MCP server must be publicly reachable by URL before the orchestrator runs.** The agent runs in Anthropic's cloud and cannot reach `localhost`. A tunnel (ngrok or equivalent) is required when running the MCP server locally.
- **The agent and environment are long-lived; sessions are short-lived.** Do not create a new agent per query — it is slow and incurs unnecessary API overhead.
- **Networking mode `limited` with `allow_mcp_servers: true` is required.** Without `allow_mcp_servers`, the agent's MCP calls fail silently (no exception is raised; the tool simply returns no data).
