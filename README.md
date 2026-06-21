# Argentine Economic Data — MCP + Managed Agents

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | System design, components and data flow |
| [Structure](docs/structure.md) | Project organization and module responsibilities |
| [Installation](docs/installation.md) | Requirements and steps to run the project |
| [Technical decisions](docs/decisions.md) | Trade-offs and design justifications |
| [Usage guide](docs/usage.md) | How to use the CLI, web UI, and MCP tools |
| [API](docs/api.md) | MCP tools and web backend endpoints |

---

## Description

This project exposes Argentine economic and financial data (exchange rates, inflation, interest rates, etc.) through a **Model Context Protocol (MCP) server**, and provides an **AI agent** powered by Anthropic's Managed Agents API that answers natural-language questions using exclusively that data.

The system solves the problem of getting accurate, up-to-date Argentine economic data through a conversational interface: instead of navigating spreadsheets or APIs, you ask "What is the blue dollar today?" and the agent fetches the exact value from the dataset and reports it with its unit and date.

**Real use case:** a developer or analyst queries live Argentine financial series (official exchange rate, blue dollar, MEP, CCL, inflation index, etc.) by chatting with an agent that never invents numbers and always cites its source.

## Quick start

```bash
# 1. Start the MCP server (Docker required)
cd MCP
cp .env.example .env
docker compose up --build

# 2. Expose it publicly (ngrok tunnel, in a second terminal or via Docker profile)
docker compose --profile tunnel up --build
# Open http://localhost:4040 to get the public URL, e.g. https://abcd-1234.ngrok-free.app

# 3. Run the agent (Python 3.10+ required)
cd ../managed_agents
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set ANTHROPIC_API_KEY and MCP_URL=https://abcd-1234.ngrok-free.app/mcp

python orchestrator.py "What is the current blue dollar rate?"
```

## Technologies used

**MCP server**
- Python 3.12
- `mcp[cli]` (FastMCP, streamable-http transport)
- `httpx` (async HTTP client for dataset downloads)
- Docker + Docker Compose
- ngrok (optional tunnel)

**Managed Agents orchestrator**
- Python 3.10+
- `anthropic` SDK >= 0.92.0 (Managed Agents beta surface)
- `python-dotenv`
- `flask` (optional web frontend)

**Data source**
- Public GitHub raw dataset: `https://raw.githubusercontent.com/maximilianozurita/arg-financial-data/main`
- No authentication required

## Quick installation

1. **MCP server:** copy `.env.example` to `.env` inside `MCP/`, then `docker compose up --build`
2. **Expose via tunnel:** `docker compose --profile tunnel up` (requires `NGROK_AUTHTOKEN` in `.env`)
3. **Orchestrator:** create a virtualenv in `managed_agents/`, install requirements, set `ANTHROPIC_API_KEY` and `MCP_URL`, then run `orchestrator.py`

Full details in [docs/installation.md](docs/installation.md).

## Architecture summary

The project has two independent, separately deployed components:

- **MCP server** (`MCP/`): a stateless Python service that exposes three tools over HTTP. It downloads series metadata once at startup and serves data on demand from a public dataset.
- **Managed Agents orchestrator** (`managed_agents/`): a Python script (or Flask web app) that creates a Claude agent connected to the MCP server by URL, then streams agent responses to the user.

The agent runs in Anthropic's cloud infrastructure with a sandboxed environment that has network access restricted to the MCP server. It can only answer using data returned by the MCP tools — it cannot use its own knowledge for economic figures.

Full details in [docs/architecture.md](docs/architecture.md).

## Project structure

```
prueba/
├── MCP/                        # MCP server (runs in Docker)
│   ├── app/
│   │   ├── config.py           # environment variable configuration
│   │   ├── dataset.py          # HTTP client + metadata cache
│   │   ├── logging_config.py   # centralized logging setup
│   │   └── server.py           # FastMCP instance + 3 tools
│   ├── Dockerfile
│   ├── docker-compose.yml      # includes optional ngrok tunnel service
│   ├── requirements.txt
│   └── .env.example
└── managed_agents/             # orchestrator + optional web UI (runs locally)
    ├── orchestrator.py         # agent/environment lifecycle + CLI
    ├── web_app.py              # Flask backend for the web chat UI
    ├── inspect_session.py      # session inspection utility
    ├── system_prompt.txt       # agent system prompt (data-only policy)
    ├── templates/index.html    # web chat frontend
    ├── requirements.txt
    └── .env.example
```

Full details in [docs/structure.md](docs/structure.md).
