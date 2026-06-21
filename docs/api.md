# API

This project exposes two distinct interfaces: the **MCP tools** consumed by the Claude agent, and the **web backend endpoints** consumed by the browser chat UI.

---

## MCP Tools

The MCP server runs at `http://HOST:PORT/mcp` using the streamable-http transport. These tools are called by the Claude agent automatically, not directly by users.

### `list_series()`

Returns the full catalog of available economic series. No network request is made — this reads from the in-memory metadata loaded at startup.

**Parameters:** none

**Returns:** array of objects

```json
[
  {
    "nombre": "Dólar Blue (Venta)",
    "slug": "dolar_blue_venta",
    "categoria": "cambiario",
    "unidad": "ARS/USD",
    "frecuencia": "diaria",
    "descripcion": ""
  }
]
```

**Use this tool first** to discover available series and their slugs before calling the other tools.

---

### `get_latest_value(slug)`

Returns the most recent published value for a series.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `slug` | string | Series identifier. Obtain from `list_series()`. |

**Returns:** object

```json
{
  "slug": "dolar_blue_venta",
  "nombre": "Dólar Blue (Venta)",
  "valor": 1475.0,
  "unidad": "ARS/USD",
  "fecha": "2026-06-17"
}
```

**Errors (as MCP ToolError):**
- `slug` is empty or not a string → "El parámetro 'slug' es obligatorio."
- `slug` not found in catalog → "No existe ninguna serie con slug '…'. Usá list_series() para ver los slugs disponibles."
- Series has no published latest value → "No hay un último valor publicado para la serie '…'."
- Network failure downloading `latest.json` → "Fallo de red al consultar el dataset. Intentá nuevamente más tarde."
- HTTP error from the dataset → "No se pudo obtener el recurso solicitado (estado <code>). Puede que la serie no tenga datos publicados."

---

### `get_series_data(slug, desde, hasta)`

Returns the historical time series for a given slug, filtered to the requested date range.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `slug` | string | Series identifier. Obtain from `list_series()`. |
| `desde` | string | Start date, inclusive. Format: `YYYY-MM-DD`. |
| `hasta` | string | End date, inclusive. Format: `YYYY-MM-DD`. |

**Returns:** object

```json
{
  "slug": "dolar_blue_venta",
  "nombre": "Dólar Blue (Venta)",
  "unidad": "ARS/USD",
  "desde": "2024-01-01",
  "hasta": "2024-01-31",
  "cantidad": 22,
  "puntos": [
    {"fecha": "2024-01-02", "valor": 1010.0},
    {"fecha": "2024-01-03", "valor": 1015.0}
  ]
}
```

`puntos` is sorted by date ascending. Values that cannot be parsed as floats are returned as strings. Rows with a malformed date in the CSV are silently skipped.

**Errors (as MCP ToolError):**
- Invalid or empty `slug` → same slug validation as `get_latest_value`
- `desde` or `hasta` is not a valid `YYYY-MM-DD` date → "La fecha '…' en '…' no es válida. Usá el formato YYYY-MM-DD (ej: 2024-01-31)."
- `desde` is later than `hasta` → "El rango es inválido: 'desde' (…) es posterior a 'hasta' (…)."
- No data points found in the requested range → "La serie '…' no tiene datos entre … y …."
- Network or HTTP errors → same messages as `get_latest_value`

---

## Web Backend Endpoints

`web_app.py` exposes a minimal Flask HTTP API consumed by `templates/index.html`. The Flask server runs on `http://127.0.0.1:5000`.

### `GET /`

Returns the chat UI HTML page.

**Response:** `text/html` — the contents of `templates/index.html`

---

### `POST /api/session`

Creates a new Managed Agent session for a conversation.

**Request body:** none (empty POST)

**Response:** `application/json`

```json
{
  "session_id": "sesn_01Uv3837JFJaS98NUUwkmUFU",
  "console_url": "https://platform.claude.com/workspaces/default/sessions/sesn_01Uv3837JFJaS98NUUwkmUFU"
}
```

Call this once at page load and once per "New conversation" action. The `console_url` links to the live session view in the Anthropic Console (requires access to the organization linked to the API key).

---

### `POST /api/chat`

Sends a message to an existing session and streams the agent's response as Server-Sent Events.

**Request body:** `application/json`

```json
{
  "session_id": "sesn_01Uv3837JFJaS98NUUwkmUFU",
  "message": "What is the current blue dollar rate?"
}
```

**Response:** `text/event-stream` — a stream of SSE frames, each a JSON object on a `data:` line.

**Event types:**

| `type` | Additional fields | Description |
|--------|-------------------|-------------|
| `text` | `text: string` | Partial agent response text. Append to the current message bubble. |
| `tool` | `name: string` | The agent called an MCP tool. Display as a chip or annotation. |
| `done` | — | The agent turn is complete. Close the stream and re-enable the input. |
| `error` | `message: string` | An API or session error occurred. Display in the UI and close the stream. |

The stream ends when a `done` or `error` event is received. The UI must open the stream to read events before enabling the next send action — sending a new message while the stream is open for a session is not supported.

**SSE frame example:**

```
data: {"type": "text", "text": "El dólar blue"}

data: {"type": "tool", "name": "get_latest_value"}

data: {"type": "text", "text": " cotiza a 1.475,00 ARS/USD al 2026-06-17."}

data: {"type": "done"}
```

---

## Dataset URLs (internal, not user-facing)

The MCP server fetches data from:

| Resource | URL path |
|----------|----------|
| Series catalog | `/metadata.json` |
| Latest values for all series | `/latest.json` |
| Historical CSV for a series | `/data/{categoria}/{slug}.csv` |

Base URL: `https://raw.githubusercontent.com/maximilianozurita/arg-financial-data/main` (configurable via `DATASET_BASE_URL`).
