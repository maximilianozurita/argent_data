# Orquestador — Claude Managed Agents + MCP de datos económicos (Argentina)

Script Python efímero (se corre a mano) que usa el SDK de Anthropic — superficie
**Managed Agents (beta)** — para crear/reusar un agente, conectarlo a un servidor
MCP externo, mandarle una pregunta y mostrar la respuesta en **streaming**,
anunciando qué tool usa en cada paso.

El agente responde **solo** con los datos que obtiene de las tools del MCP
(`list_series`, `get_latest_value`, `get_series_data`). Es un proveedor de datos,
no un asesor.

## Piezas separadas: orquestador vs MCP

- **Este orquestador** NO va en Docker: es un script que se corre a mano.
- **El servidor MCP** es una pieza aparte que corre como servicio (Docker + túnel)
  y expone sus tools por una URL pública.

> ⚠️ **El MCP tiene que estar levantado y expuesto por URL (HTTP/SSE) ANTES de
> correr el orquestador.** El orquestador solo se conecta a esa URL (`MCP_URL`).

## Requisitos

- Python 3.10+
- `ANTHROPIC_API_KEY` (https://platform.claude.com/)
- `MCP_URL`: URL pública del MCP, ya levantado y alcanzable.

## Setup (virtualenv, sin Docker)

```bash
cd managed_agents
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # luego completá ANTHROPIC_API_KEY y MCP_URL
```

## Correr

```bash
# Pregunta por argumento:
python orchestrator.py "¿Cuál es el último valor del dólar oficial?"

# Sin argumento: la pide por consola (input()):
python orchestrator.py

# Forzar recreación del agente/environment (p. ej. si cambiaste el system prompt):
python orchestrator.py --reset "¿Cuál es el último valor del dólar oficial?"
```

El script imprime una **URL de consola** para ver la sesión en vivo, va mostrando
el texto del agente a medida que llega, y marca cada uso de tool con
`[MCP tool: ...]`. Tras cada respuesta podés mandar un follow-up (útil cuando el
agente pregunta "¿cuál serie?"); Enter vacío o `exit` termina.

## Reuso del agente (crear una vez, reusar por ID)

- La **primera corrida** crea el agente y el environment y guarda sus IDs en
  `.agent_config.json` (gitignored).
- Las **corridas siguientes** leen esos IDs y van directo a crear la sesión, sin
  volver a crear el agente.
- Para **recrear** desde cero: borrá `.agent_config.json` o usá `--reset`.

## Cambiar el modelo

Editá la constante `MODEL` en `orchestrator.py` (por defecto `claude-haiku-4-5`).

## Networking / gotcha del MCP

Por defecto el environment usa networking `limited` con `allow_mcp_servers=True`
(egress restringido salvo el MCP del agente). Si las tools del MCP devuelven datos
vacíos **sin** lanzar error, casi siempre es la trampa de networking: cambiá
`NETWORKING_MODE` a `"unrestricted"` en `orchestrator.py` (y recreá con `--reset`).

## Determinismo

Managed Agents no expone un parámetro de `temperature` en la config del agente.
El comportamiento determinista (p. ej. ante "el dólar" siempre pedir aclaración en
vez de asumir) se logra con la **regla fija definida en `system_prompt.txt`**.

## Frontend web (chat con streaming)

Además del CLI hay un frontend de chat: un backend Flask (`web_app.py`) que reusa
`orchestrator.py` y una página (`templates/index.html`). El navegador habla solo
con el backend; la `ANTHROPIC_API_KEY` queda del lado del servidor.

```bash
source .venv/bin/activate
pip install -r requirements.txt          # incluye flask
python web_app.py                         # http://127.0.0.1:5000
```

Abrí http://127.0.0.1:5000, escribí la pregunta y vas a ver la respuesta en vivo,
con un chip ⚙ por cada tool del MCP que usa el agente. "Nueva conversación" crea
una sesión nueva; "Ver sesión ↗" abre la consola (si tenés acceso a la cuenta).

Arquitectura: cada conversación = una sesión (`POST /api/session`); cada mensaje
abre el stream del agente y reenvía los eventos al navegador como SSE
(`POST /api/chat`). Las tools del MCP se autorizan automáticamente (solo lectura).
El agente/environment se reusan vía `.agent_config.json` igual que en el CLI.

## Notas de la API beta

Managed Agents está en beta (`managed-agents-2026-04-01`; el SDK setea el header
solo). La API puede cambiar. Si al correr aparece que falta `client.beta.agents`,
actualizá el SDK: `pip install -U anthropic`.
