# Installation

The project has two independent components. The MCP server must be running and publicly reachable before the orchestrator can be used.

## Prerequisites

**MCP server**
- Docker and Docker Compose (any recent version)
- (Optional) ngrok account for the built-in tunnel: https://dashboard.ngrok.com/get-started/your-authtoken

**Managed Agents orchestrator**
- Python 3.10 or later
- An Anthropic API key with access to the Managed Agents beta: https://platform.claude.com/
- The MCP server running and reachable via a public URL

## Step 1: Clone the repository

```bash
git clone <repository-url>
cd prueba
```

## Step 2: Set up and start the MCP server

```bash
cd MCP
cp .env.example .env
```

The default `.env` values work without modification — the dataset is public and requires no credentials. Adjust only if you need a different port or want to point to a different dataset.

```bash
docker compose up --build
```

Verify it is running:

```bash
curl http://localhost:8000/mcp
```

You should receive an MCP protocol response (not a 404 or connection error).

## Step 3: Expose the MCP server via a public tunnel

The Claude agent runs in Anthropic's cloud and cannot reach `localhost`. You must expose the MCP server via a public HTTPS URL.

### Option A — ngrok inside Docker Compose (recommended for quick setup)

Add your ngrok auth token to `MCP/.env`:

```
NGROK_AUTHTOKEN=your_token_here
```

Then start with the tunnel profile:

```bash
docker compose --profile tunnel up --build
```

Open http://localhost:4040 in a browser. Copy the HTTPS forwarding URL shown there (e.g., `https://abcd-1234.ngrok-free.app`). The MCP endpoint is that URL plus `/mcp`:

```
https://abcd-1234.ngrok-free.app/mcp
```

### Option B — ngrok manually (if the MCP server is already running)

```bash
ngrok http 8000
```

Copy the HTTPS URL printed by ngrok and append `/mcp`.

### Option C — Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the HTTPS URL and append `/mcp`.

## Step 4: Set up the orchestrator

```bash
cd ../managed_agents
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `managed_agents/.env` and fill in both values:

```
ANTHROPIC_API_KEY=sk-ant-...
MCP_URL=https://abcd-1234.ngrok-free.app/mcp
```

`MCP_URL` must be the full URL including the `/mcp` path suffix.

## Step 5: Run the orchestrator

```bash
# With a question as an argument:
python orchestrator.py "What is the current blue dollar rate?"

# Interactive mode (prompts for a question):
python orchestrator.py
```

On the first run, the orchestrator creates an agent and environment in your Anthropic account and saves their IDs to `.agent_config.json`. Subsequent runs reuse those resources.

Expected output (first run):

```
[setup] creando agente...
[setup] creando environment...
[setup] guardado en .agent_config.json: {agent_id: ..., environment_id: ...}
[sesión] sesn_...
[en vivo] https://platform.claude.com/workspaces/default/sessions/sesn_...

> What is the current blue dollar rate?

[MCP tool: list_series]
[MCP tool: get_latest_value]
El dólar blue (venta) cotiza a 1.475,00 ARS/USD al 2026-06-17.
```

## Step 6 (optional): Run the web frontend

```bash
source .venv/bin/activate
python web_app.py
```

Open http://127.0.0.1:5000 in a browser.

## Environment variables reference

### MCP server (`MCP/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Interface the server listens on. Keep `0.0.0.0` inside Docker. |
| `PORT` | `8000` | Port for the MCP server. |
| `DATASET_BASE_URL` | `https://raw.githubusercontent.com/maximilianozurita/arg-financial-data/main` | Base URL of the public dataset (no trailing slash). |
| `LOG_LEVEL` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, or `ERROR`. Use `DEBUG` to see each HTTP download. |
| `NGROK_AUTHTOKEN` | *(empty)* | Required only for the optional ngrok service (`--profile tunnel`). |

### Orchestrator (`managed_agents/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | yes | Your Anthropic API key. |
| `MCP_URL` | yes | Full public URL of the MCP endpoint, including `/mcp` path. |

## Verifying the setup

Check that the MCP tools are reachable before running the orchestrator:

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client("http://localhost:8000/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print([t.name for t in tools.tools])
            # Expected: ['list_series', 'get_latest_value', 'get_series_data']

asyncio.run(test())
```

Run this with the MCP SDK installed (`pip install mcp[cli]`).

## Resetting the agent

If you change `system_prompt.txt`, the model constant, or the MCP URL in `orchestrator.py`, you must recreate the agent:

```bash
python orchestrator.py --reset "your question"
```

This deletes `.agent_config.json` and creates a new agent and environment from scratch.
