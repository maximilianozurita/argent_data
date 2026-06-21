# Technical Decisions

## MCP transport: streamable-http instead of SSE

The MCP Python SDK supports two HTTP transports: the older SSE-based transport (endpoint `/sse`) and the current streamable-http transport (endpoint `/mcp`). This project uses streamable-http because it is the transport recommended by the MCP SDK for new servers and is what the Anthropic Managed Agents infrastructure expects when connecting to an MCP server by URL.

The SSE transport is being phased out. Using streamable-http avoids a future migration and ensures compatibility with agents connecting via the Anthropic API.

## Stateless HTTP mode (`stateless_http=True, json_response=True`)

The FastMCP instance is configured for stateless HTTP. This is appropriate because the consumer is a remote agent that opens a new connection per tool call through a tunnel — there is no persistent SSE session to maintain. Stateless mode also simplifies deployment: the server can run behind a load balancer without session affinity.

The `json_response=True` option returns tool results as plain JSON rather than MCP streaming responses, which is what the Anthropic agent infrastructure parses when calling tools over HTTP.

## Metadata loaded once at startup, not cached with TTL

`metadata.json` is downloaded exactly once when the server starts (`lifespan`) and kept in the `METADATA` dict for the server's lifetime. It is never refreshed.

The alternative — downloading it per request or on a TTL — was rejected because the metadata (series catalog, slugs, categories, units) changes infrequently. The simplest correct behavior is to restart the container when the catalog changes. A restart is a deliberate operator action, not something that should happen transparently mid-session. This also eliminates concurrency concerns around cache invalidation.

`load_metadata()` is idempotent (checks `if METADATA` before downloading) to handle the edge case where stateless HTTP mode triggers the lifespan multiple times.

## Single shared `httpx.AsyncClient` for per-request downloads

`latest.json` and CSV files are fetched with a single `AsyncClient` instance that is created lazily and reused. The alternative — creating a new client per tool call — works but wastes connection setup overhead for every request.

`metadata.json` uses its own short-lived client (via `async with _new_client()`) because it is called from `asyncio.run()` at startup, outside the event loop that will serve requests. Using the global client there would risk creating it in the wrong event loop.

## Error messages: safe to the agent, detailed in logs

All exceptions from network or HTTP operations are caught in `dataset.py` and re-raised as `DatasetError` with a message that is safe for the agent to receive — no internal URLs, status codes (except the HTTP status itself), or stack traces. The actual exception is logged at `WARNING` or `ERROR` level with full detail.

This separation exists because the agent may include error messages in its response to the user. Exposing internal URLs or technical error strings in those responses would be confusing to end users and could leak infrastructure details.

## Agent and environment created once, reused by ID

The Managed Agents API charges for agent and environment creation. More practically, creating them takes several seconds. The "create once, reuse by ID" pattern — persisting `agent_id` and `environment_id` in `.agent_config.json` — reduces latency for all runs after the first and makes the system more predictable.

The `.agent_config.json` file is gitignored to prevent team members from inadvertently sharing agent resources across accounts.

`--reset` provides an explicit escape hatch when recreation is needed (model change, system prompt update, or stale IDs after resources are deleted from the Anthropic account).

## Networking mode: `limited` with `allow_mcp_servers: true`

The Managed Agent environment uses `limited` networking — all egress is blocked by default except to MCP servers registered on the agent. This is a security boundary: the agent cannot make arbitrary outbound requests.

`unrestricted` networking was considered as a simpler option but rejected because it allows the agent to make requests to any host, which is unnecessary given that the agent only needs to reach the MCP server.

The critical gotcha documented in the code: with `limited` networking but **without** `allow_mcp_servers: true`, MCP tool calls fail silently — the agent receives no data and no error. This was an observed failure mode during development and is now documented in the orchestrator and README.

## Stream-first event loop

The orchestrator opens the event stream **before** sending the user message. This is a requirement of the Managed Agents API: sending the message first risks losing the initial events from the stream if there is any latency opening the stream connection.

## Deterministic ambiguity resolution via system prompt rule

The agent model (Claude Haiku) does not expose a `temperature` parameter through the Managed Agents API. Consistent behavior for ambiguous queries (e.g., "the dollar" matching multiple series) is enforced through an explicit rule in `system_prompt.txt`: the agent must always call `list_series`, identify all matching series, and ask the user to specify before returning a value. This rule is stated as fixed and deterministic in the prompt, which makes the behavior consistent regardless of model stochasticity.

## Flask for the web backend, not FastAPI or async frameworks

The web backend (`web_app.py`) uses Flask because:
1. The orchestrator logic (`orchestrator.py`) is synchronous — it uses the blocking Anthropic SDK stream iterator, not an async client.
2. Flask's `threaded=True` mode handles concurrent requests (session creation + chat stream) without requiring async.
3. Flask has minimal overhead for a project where the bottleneck is always the upstream API.

`use_reloader=False` is set explicitly to prevent Flask's auto-reloader from running the agent/environment setup code twice on startup.

## No tests

There are no automated tests in this repository. The system's correctness depends heavily on external APIs (Anthropic, GitHub dataset) that are difficult to mock meaningfully at the integration level. The MCP tools have straightforward input validation tested manually via the MCP Inspector. Adding unit tests for the validation helpers (`_require_slug`, `_parse_date`) and CSV parsing logic would be the highest-value starting point for a test suite.
