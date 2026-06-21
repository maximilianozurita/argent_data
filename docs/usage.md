# Usage Guide

Assumes the MCP server is running and the orchestrator is set up. See [installation.md](installation.md) if you haven't done that yet.

---

## CLI — asking a single question

```bash
cd managed_agents
source .venv/bin/activate
python orchestrator.py "What is the current blue dollar rate?"
```

The agent will:
1. Print `[sesión] sesn_...` and a link to the live session in the Anthropic Console.
2. Show `[MCP tool: ...]` each time it calls a tool.
3. Stream the answer as it is generated.

After the answer, you are prompted for a follow-up question. Press Enter without typing anything, or type `exit`, to quit.

---

## CLI — interactive mode

```bash
python orchestrator.py
```

Prompts `Pregunta: ` and waits for input. Behavior is the same as passing the question as an argument.

---

## CLI — forced agent recreation

Use `--reset` when you have changed `system_prompt.txt`, the agent model (`AGENT_MODEL`), or when `.agent_config.json` contains stale IDs (resources deleted from the Anthropic account):

```bash
python orchestrator.py --reset "What is the latest inflation index?"
```

This deletes `.agent_config.json` and creates a fresh agent and environment.

---

## Web UI

```bash
source .venv/bin/activate
python web_app.py
```

Open http://127.0.0.1:5000 in a browser.

- Type a question and press Enter or click "Enviar".
- The agent's response streams in real time. Each MCP tool call appears as a chip (e.g., `⚙ get_latest_value`) above the response text.
- "Nueva conversación" creates a new session — previous messages are cleared and the agent starts fresh.
- "Ver sesión ↗" opens the live session view in the Anthropic Console (visible only if you have access to the organization linked to the API key).

---

## Common query patterns

### Get the latest value of a series

If you know the series name:

```
What is the current blue dollar rate?
What is today's official dollar?
What is the latest MEP dollar value?
```

If the query is ambiguous (e.g., "the dollar" could be blue, official, MEP, or CCL), the agent will call `list_series`, identify all matching series, and ask you to specify. This is by design — the agent never assumes which series you meant.

### Query a specific time range

```
What was the blue dollar in January 2024?
Give me the inflation index from 2023-01-01 to 2023-12-31.
```

The agent will call `get_series_data` with the appropriate slug and date range, and return a list of `{fecha, valor}` data points.

### Calculate a percentage change

```
What was the percentage change in the blue dollar between January 2024 and June 2024?
```

The agent will fetch the series for the full range, extract the start and end values, and show the calculation explicitly: starting value, ending value, dates, and the formula `(end - start) / start * 100`.

### Discover available series

```
What series are available?
What data can you query?
```

The agent will call `list_series` and summarize the catalog. You can then ask about a specific series using its name or slug.

---

## Inspecting a past session

If you have a session ID (printed at the start of each CLI run), you can inspect its full event transcript:

```bash
python inspect_session.py sesn_01Uv3837JFJaS98NUUwkmUFU
```

Output shows session status, usage, and a chronological transcript of all events: agent messages, MCP tool calls with their inputs, tool results, and status transitions. Useful for debugging without access to the Anthropic Console.

---

## Common errors and solutions

**"Falta la variable de entorno MCP_URL"**

The `.env` file is missing or `MCP_URL` is not set. Copy `.env.example` to `.env` and fill in the value.

**"Error de autenticación: revisá ANTHROPIC_API_KEY"**

The API key is invalid, expired, or missing. Verify the key at https://platform.claude.com/.

**"Recurso no encontrado … Quizá el agente/environment guardado en .agent_config.json ya no existe. Probá con --reset."**

The agent or environment IDs in `.agent_config.json` no longer exist in the Anthropic account (they may have been deleted via the Console or API). Run with `--reset` to recreate them.

**Agent responds but returns no data (empty answers, or "I don't have data for that")**

The most common cause is a networking misconfiguration in the environment. Verify that `NETWORKING_MODE` is `"limited"` (default) and that the environment was created with `allow_mcp_servers: true`. If you previously created the environment with `"unrestricted"` mode and changed it in code, you must run `--reset` — the environment config is set at creation time and cannot be updated.

**MCP tool calls fail with a network error**

The `MCP_URL` may be unreachable from the Anthropic cloud. Verify that the tunnel (ngrok or equivalent) is running and that the URL in `.env` includes the `/mcp` path. The ngrok inspector at http://localhost:4040 shows live requests to verify connectivity.

**"Tu versión de 'anthropic' no expone client.beta.agents"**

The installed `anthropic` SDK is too old to support Managed Agents. Upgrade it:

```bash
pip install -U anthropic
```

---

## Changing the agent model

The model is read from the `AGENT_MODEL` environment variable, so you can switch models without editing the code. Set it in `managed_agents/.env`:

```
# managed_agents/.env
AGENT_MODEL=claude-opus-4-8
```

If `AGENT_MODEL` is unset, the orchestrator falls back to a fast, cost-efficient default (`claude-haiku-4-5`). The constant in `managed_agents/orchestrator.py` reflects this:

```python
MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5")
```

After changing the model, run with `--reset` to apply the change to the agent.
