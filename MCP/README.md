# MCP · Datos económicos argentinos

Servidor [MCP](https://modelcontextprotocol.io) en Python que expone un dataset
público de datos económicos argentinos como **tools**, para ser consumido por un
**agente remoto vía URL**. Corre en Docker y usa transporte **streamable-http**
(la forma HTTP vigente del SDK de MCP), por lo que el endpoint queda en `/mcp`.

Los datos se leen por HTTP desde un dataset público (sin autenticación):
`https://raw.githubusercontent.com/maximilianozurita/arg-financial-data/main`

## Tools expuestas

| Tool | Para qué sirve | Devuelve |
|------|----------------|----------|
| `list_series()` | El "menú": qué series se pueden consultar y sus slugs. No hace descargas (lee de memoria). | Lista de `{nombre, slug, categoria, unidad, frecuencia, descripcion}` |
| `get_latest_value(slug)` | El dato más reciente de una serie (ej: dólar blue de hoy). | `{slug, nombre, valor, unidad, fecha}` |
| `get_series_data(slug, desde, hasta)` | La serie histórica entre dos fechas (`YYYY-MM-DD`, inclusive). | `{slug, nombre, unidad, desde, hasta, cantidad, puntos:[{fecha, valor}]}` |

Al arrancar, el servidor descarga `metadata.json` **una sola vez** y mantiene en
memoria el mapa `slug -> {categoria, nombre, unidad, frecuencia, descripcion}`.
`latest.json` y los CSV se descargan en cada llamada.

## 1. Levantar el MCP

Requisitos: Docker y Docker Compose.

```bash
cp .env.example .env        # ajustá valores si querés (no contiene secretos)
docker compose up --build
```

El servidor queda escuchando en:

```
http://localhost:8000/mcp
```

> El puerto y la URL base del dataset se configuran por variables de entorno
> (`PORT`, `HOST`, `DATASET_BASE_URL`). Ver `.env.example`.

## 2. Exponerlo a un agente en la nube (túnel)

El contenedor corre en tu `localhost`, pero el agente que lo consume corre en la
nube. Para que sea alcanzable necesitás un **túnel** que te dé una URL pública.

### Opción A — ngrok dentro del compose (opcional)

1. Conseguí tu token en https://dashboard.ngrok.com/get-started/your-authtoken
	y ponelo en `.env` como `NGROK_AUTHTOKEN=...`.
2. Levantá todo con el profile `tunnel`:

	```bash
	docker compose --profile tunnel up --build
	```

3. Abrí el inspector de ngrok en http://localhost:4040 y copiá la URL pública
	(algo como `https://abcd-1234.ngrok-free.app`).
4. La URL que le pasás al agente es esa **+ `/mcp`**:

	```
	https://abcd-1234.ngrok-free.app/mcp
	```

> El servicio `ngrok` es **opcional**: solo arranca con `--profile tunnel`.
> Sin ese flag, `docker compose up` levanta únicamente el MCP.

### Opción B — túnel manual

Con el MCP ya corriendo (`docker compose up`), en otra terminal:

```bash
ngrok http 8000
# o, con Cloudflare:
# cloudflared tunnel --url http://localhost:8000
```

Tomá la URL pública que te imprime y agregale `/mcp`.

## 3. Probar las tools localmente (antes de conectar el agente)

Con el servidor corriendo en `http://localhost:8000/mcp`:

### Opción A — MCP Inspector (UI)

```bash
npx @modelcontextprotocol/inspector
```

En la UI elegí transporte **Streamable HTTP**, URL `http://localhost:8000/mcp`,
conectá y probá las tools.

### Opción B — Cliente Python

Con las dependencias instaladas (`pip install -r requirements.txt`):

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
	 async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
		  async with ClientSession(read, write) as session:
				await session.initialize()

				print("Tools:", [t.name for t in (await session.list_tools()).tools])

				print(await session.call_tool("list_series", {}))
				print(await session.call_tool("get_latest_value", {"slug": "dolar_blue_venta"}))
				print(await session.call_tool("get_series_data", {
					 "slug": "dolar_blue_venta",
					 "desde": "2024-01-01",
					 "hasta": "2024-01-31",
				}))


asyncio.run(main())
```

Casos de error esperados (devuelven un error legible, no un crash):

- `get_latest_value("no_existe")` → "No existe ninguna serie con slug 'no_existe'…"
- `get_series_data("dolar_blue_venta", "2024-13-01", "2024-01-31")` → fecha inválida.
- Rango sin datos → "… no tiene datos entre … y …".

## Estructura

```
.
├── app/
│   ├── config.py     # variables de entorno (HOST, PORT, DATASET_BASE_URL)
│   ├── dataset.py    # cliente httpx, carga de metadata, descargas
│   └── server.py     # FastMCP + las 3 tools + lifespan
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Interfaz de escucha (dejar `0.0.0.0` en contenedor). |
| `PORT` | `8000` | Puerto del servidor MCP. |
| `DATASET_BASE_URL` | URL raw del dataset | Base del dataset (sin barra final). |
| `LOG_LEVEL` | `INFO` | Nivel de logging (`DEBUG`/`INFO`/`WARNING`/`ERROR`). `DEBUG` muestra cada descarga HTTP. |
| `NGROK_AUTHTOKEN` | *(vacío)* | Solo para el túnel ngrok opcional. |

## Logs / debugging

El servidor loguea a **stdout** (visible con `docker compose logs -f`). Por cada
llamada se registra la tool invocada, sus parámetros, el resultado (o el error) y
las validaciones que fallan. Los errores internos (HTTP/red) se loguean con su
detalle real, mientras que el mensaje que recibe el agente queda genérico y seguro.

Ejemplo de salida:

```
2026-06-20 20:30:01 INFO    [app.server] tool=get_latest_value slug=dolar_blue_venta
2026-06-20 20:30:01 INFO    [app.server] tool=get_latest_value slug=dolar_blue_venta ok -> valor=1475.0 fecha=2026-06-17
2026-06-20 20:30:05 WARNING [app.server] Validación: slug inexistente 'no_existe'
```

Para ver cada descarga HTTP al dataset, poné `LOG_LEVEL=DEBUG` en `.env`.
