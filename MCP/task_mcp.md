## Descripción
Construí un servidor MCP en Python que exponga un dataset público de datos
económicos argentinos como herramientas, para ser consumido por un agente
remoto vía URL. Tiene que correr en un contenedor Docker.

CONTEXTO DEL DATASET
Los datos se consumen por HTTP desde esta base (pública, sin autenticación):
https://raw.githubusercontent.com/maximilianozurita/arg-financial-data/main
- metadata.json : catálogo de series. Cada entrada tiene: nombre, fuente,
  categoria, unidad, frecuencia, descripcion, slug.
- latest.json : último valor de cada serie.
- data/{categoria}/{slug}.csv : serie histórica individual. Formato: columnas
  "fecha,valor". Ejemplo de ruta: data/cambiario/dolar_blue_venta.csv
La ruta de cada CSV se arma como data/{categoria}/{slug}.csv usando los campos
del metadata.

STACK
- SDK oficial de MCP para Python.
- Transporte HTTP/SSE (NO stdio), porque lo consume un agente remoto por URL.
  IMPORTANTE: verificá la API vigente del SDK de MCP para el transporte HTTP,
  puede haber cambiado; usá la forma actual. Preferentemente fastMCP
- Puerto configurable por variable de entorno (default 8000).
- La URL base del dataset configurable por variable de entorno, con el default
  de arriba.

COMPORTAMIENTO
- Al arrancar, descargá metadata.json UNA vez y mantené en memoria un mapa
  slug -> {categoria, nombre, unidad, frecuencia, descripcion}. Usalo para
  resolver rutas y para list_series. No lo descargues en cada llamada.

TOOLS (tres, de responsabilidad única)
1. list_series() : devuelve el catálogo completo desde el metadata en memoria.
   Por cada serie devolvé nombre, slug, categoria, unidad, frecuencia y
   descripcion. Esta tool le da al agente el menú de qué puede consultar.
2. get_latest_value(slug) : descarga latest.json, devuelve el último valor de
   esa serie junto con su unidad y la fecha del dato. Validá que el slug exista.
3. get_series_data(slug, desde, hasta) : resolvé la categoria del slug desde el
   mapa en memoria, armá la ruta data/{categoria}/{slug}.csv, descargá el CSV,
   filtrá las filas por el rango de fechas [desde, hasta] (formato YYYY-MM-DD),
   y devolvé la lista de puntos {fecha, valor} más la unidad de la serie.
   Validá que el slug exista y que las fechas sean válidas.

ROBUSTEZ Y SEGURIDAD
- Toda descarga HTTP envuelta en manejo de errores; devolvé errores
  estructurados y legibles para el agente (slug inexistente, serie sin datos en
  el rango, fallo de red), sin exponer detalles internos.
- Validá los parámetros de cada tool antes de usarlos.
- No hay credenciales: el dataset es público. No agregues manejo de secretos.
- Las descripciones de cada tool (las que ve el agente) tienen que ser claras y
  explicar cuándo usarla y qué devuelve, porque de eso depende que el agente
  las invoque bien.

DOCKER
- Dockerfile para el servidor.
- docker-compose.yml que levante el servicio del MCP exponiendo el puerto.
- IMPORTANTE: el contenedor corre en localhost, pero el agente que lo consume
  corre en la nube. Para que sea alcanzable hace falta un túnel (ngrok o
  Cloudflare). Documentá esto claramente en el README: cómo levantar el MCP con
  docker-compose y cómo exponerlo con un túnel para obtener la URL pública.
  Si podés, incluí en el compose un servicio opcional de cloudflared/ngrok,
  pero dejá claro que es opcional y configurable.

ENTREGABLES
- Código del servidor, estructurado y comentado.
- Dockerfile y docker-compose.yml.
- requirements.txt.
- .env.example SIN valores reales (puerto, URL base).
- README con: cómo levantar el MCP, cómo exponerlo con túnel, y cómo probar las
  tools localmente antes de conectarlo al agente.

No incluyas datos reales en ningún archivo.

## Flujo de desarrollo:
Primero investiga todo lo necesario para la tarea, luego se arma un plan haciendo las preguntas pertinentes sobre la tecnologia a utilizar, el sistema de directorios, la arquitectura, etc. Si hay cambios en el plan se modifica este archivo y se van logueando las decisiones. Luego, cuando ya esta todo ok, se pregunta si ejecutar el plan para comenzar a realizar los cambios. Todo se va logueando en este archivo.

## Decisiones
<!-- Una subsección por cada decisión no trivial tomada durante el planning -->

### Decisión 1: SDK y transporte HTTP
- **Elegida:** FastMCP (`from mcp.server.fastmcp import FastMCP`) con transporte
  `streamable-http` (`mcp.run(transport="streamable-http")`). Endpoint en `/mcp`.
  Verificado contra la doc vigente del SDK (paquete PyPI `mcp`, probado con `mcp 1.28.0`).
- **Descartadas:** transporte SSE (legacy, reemplazado por streamable-http); stdio
  (no sirve para un agente remoto vía URL).

### Decisión 2: Modo del servidor HTTP
- **Elegida:** `stateless_http=True, json_response=True`. Ideal para un agente
  remoto que abre una conexión por llamada a través de un túnel; no requiere
  mantener sesión/stream persistente.
- **Descartadas:** modo stateful con sesión (más frágil detrás de un túnel).

### Decisión 3: Túnel para exponer a la nube
- **Elegida:** ngrok como servicio **opcional** del compose, activado con
  `--profile tunnel`. Token vía `NGROK_AUTHTOKEN` en `.env`.
- **Descartadas:** cloudflared (igual de válido; se documenta como alternativa
  manual en el README); incluir ambos (ruido innecesario).

### Decisión 4: Estructura del código
- **Elegida:** paquete modular `app/` (`config.py` env vars, `dataset.py` capa de
  datos, `server.py` FastMCP + tools). Más limpio y testeable.
- **Descartadas:** un único `server.py` (menos separación de responsabilidades).

### Decisión 5: Cliente HTTP
- **Elegida:** `httpx.AsyncClient` único reutilizable (tools async). Encaja con el
  event loop de FastMCP/uvicorn.
- **Descartadas:** `requests` síncrono (correría en threadpool, menos natural).

### Decisión 6: Manejo de errores
- **Elegida:** errores internos (`httpx`, parseo) se traducen a `DatasetError` con
  mensaje seguro; las tools lo re-levantan como `ToolError` → el cliente MCP recibe
  `isError: true` con un mensaje legible, sin tracebacks ni internals.

### Decisión 7: Logging (debugging)
- **Elegida:** módulo `logging` estándar con un logger propio (`app.*`) hacia
  **stdout** (visible en `docker compose logs`), configurado en
  `app/logging_config.py`. Nivel por env var `LOG_LEVEL` (default INFO; DEBUG loguea
  cada descarga HTTP). Los errores internos se loguean con su **detalle real**
  (status HTTP, excepción), mientras que al agente le llega solo el mensaje genérico.
- **Descartadas:** prints (no configurables, sin niveles); reusar el logger de
  uvicorn (se mezcla con sus mensajes, menos control de formato).

## Casos de ejemplo
<!-- Sección donde se muestran casos de ejemplo -->
Verificados end-to-end contra el servidor corriendo en `http://127.0.0.1:8000/mcp`:

- `list_series()` → 27 series; cada una con `{nombre, slug, categoria, unidad,
  frecuencia, descripcion}`.
- `get_latest_value("dolar_blue_venta")` → `{slug, nombre:"Dólar Blue (Venta)",
  valor:1475.0, unidad:"ARS/USD", fecha:"2026-06-17"}`.
- `get_series_data("dolar_blue_venta", "2024-01-01", "2024-01-10")` → 8 puntos
  `{fecha, valor}` dentro del rango.
- Errores (todos `isError: true`, mensaje legible):
  - slug inexistente → "No existe ninguna serie con slug 'no_existe'…".
  - fecha inválida (`2024-13-01`) → "La fecha … no es válida. Usá YYYY-MM-DD…".
  - rango invertido → "El rango es inválido: 'desde' … es posterior a 'hasta'…".
  - sin datos en el rango → "La serie … no tiene datos entre … y …".

## Plan de implementación
<!-- Pasos concretos y ordenados. La ejecución los marca [x] al completar cada uno. Concentrarse en realizar una tarea a la vez -->
- [x] Paso 1: `requirements.txt`, `.env.example` (sin secretos), `.dockerignore`.
- [x] Paso 2: `app/__init__.py`, `app/config.py` (HOST, PORT, DATASET_BASE_URL).
- [x] Paso 3: `app/dataset.py` (cliente httpx, `load_metadata`, `fetch_latest`,
  `fetch_csv`, `DatasetError`).
- [x] Paso 4: `app/server.py` (FastMCP, lifespan que carga metadata, 3 tools con
  docstrings ricos, validaciones, manejo de errores, entrypoint streamable-http).
- [x] Paso 5: `Dockerfile` (python:3.12-slim, usuario no-root).
- [x] Paso 6: `docker-compose.yml` (servicio `mcp` + `ngrok` opcional con profile).
- [x] Paso 7: `README.md` (levantar, exponer con túnel, probar tools localmente).
- [x] Paso 8: registrar decisiones y log en `task_mcp.md`.
- [x] Paso 9: verificación end-to-end (las 3 tools + casos de error).

## Restricciones y gotchas
<!-- Lo no obvio que apareció en el planning y que la ejecución debe tener en cuenta.
     Este es el campo más valioso para una sesión fría. -->
- **El endpoint incluye `/mcp`**: la URL para el agente es `…/mcp`, no la raíz.
- **`HOST=0.0.0.0` dentro del contenedor** (no `127.0.0.1`), o no es alcanzable
  desde fuera.
- **FastMCP envuelve resultados de tipo lista** en `structuredContent.result`
  (no en la raíz). Los clientes deben leer de ahí (se vio al probar `list_series`).
- **CRÍTICO — el lifespan corre POR REQUEST en modo `stateless_http=True`.** No
  apoyarse en él para tareas de "una sola vez": la carga de metadata debe hacerse
  en `__main__` antes de `mcp.run()` y ser idempotente (`load_metadata()` retorna si
  `METADATA` ya está poblado). Apoyarse solo en el lifespan redescargaba
  `metadata.json` en cada llamada (bug detectado vía logging y corregido).
- **Cliente HTTP global y perezoso**, reutilizado entre requests (uvicorn corre un
  único event loop). No crearlo/cerrarlo por request (lo hacía el lifespan).
- **Solo `metadata.json` se cachea** (una vez al arrancar). `latest.json` y los CSV
  se descargan en cada llamada, según la spec.
- Filtrado de fechas **inclusive** `[desde, hasta]`; se valida formato YYYY-MM-DD
  y que `desde <= hasta`.
- **No hay datos reales embebidos** en ningún archivo del repo; los valores en
  "Casos de ejemplo" son ilustrativos del formato (salida real de la verificación).
- ngrok es **opcional** (`--profile tunnel`); sin ese flag solo levanta el MCP.

## Log de cambios
<!-- La execution session completa esta sección. Formato:
     - [fecha] Paso N: qué se cambió, en qué archivo, por qué, cada cambio en el codigo en esta sesion se debe registrar aca. Si se compacta mantener en contexto que se deben registar cambios aca -->
- [2026-06-20] Paso 1: creados `requirements.txt` (mcp[cli]>=1.9.0, httpx>=0.27),
  `.env.example` (HOST/PORT/DATASET_BASE_URL/NGROK_AUTHTOKEN, sin valores reales),
  `.dockerignore`.
- [2026-06-20] Paso 2: creados `app/__init__.py` y `app/config.py` (lee env vars,
  normaliza DATASET_BASE_URL quitando barra final).
- [2026-06-20] Paso 3: creado `app/dataset.py` — cliente httpx único reutilizable,
  `load_metadata()` (mapa slug→info en memoria), `fetch_latest()`, `fetch_csv()`,
  `DatasetError` y helper `_get_text` que traduce fallos HTTP/red a mensajes seguros.
- [2026-06-20] Paso 4: creado `app/server.py` — `FastMCP` con `host/port` desde
  config, `stateless_http=True`, `json_response=True`, lifespan que carga metadata
  al arrancar y cierra el cliente al apagar. Tres tools (`list_series`,
  `get_latest_value`, `get_series_data`) con docstrings ricos, validación de slug y
  fechas, parseo de CSV con filtrado inclusivo, errores como `ToolError`.
- [2026-06-20] Paso 5: creado `Dockerfile` (python:3.12-slim, deps cacheadas,
  usuario no-root, `CMD python -m app.server`).
- [2026-06-20] Paso 6: creado `docker-compose.yml` — servicio `mcp` (build, env_file,
  ports `${PORT:-8000}`) y servicio `ngrok` opcional bajo `profiles: ["tunnel"]`.
- [2026-06-20] Paso 7: creado `README.md` (levantar con compose, túnel ngrok/manual,
  pruebas con MCP Inspector y cliente Python, tabla de env vars y de tools).
- [2026-06-20] Paso 9: verificación con `mcp 1.28.0` en venv local. Servidor arranca
  (metadata cargada en lifespan, Uvicorn en :8000). Cliente streamable-http confirmó
  las 3 tools y los 4 casos de error. Sin cambios de código necesarios tras la prueba.
- [2026-06-20] Paso 8: completadas las secciones Decisiones, Casos de ejemplo, Plan,
  Restricciones y este Log en `task_mcp.md`.

### Sesión posterior — Docker en colima + logging + fix de metadata
- [2026-06-20] Entorno: la máquina usa el `docker` de Homebrew con **colima** (Docker
  Desktop fue removido). Para levantar el stack hubo que: instalar Compose v2
  (`brew install docker-compose` + symlink en `~/.docker/cli-plugins/`), quitar
  `"credsStore": "desktop"` de `~/.docker/config.json` (helper inexistente que rompía
  el build) e instalar buildx (`brew install docker-buildx` + symlink). Build y
  `docker compose up` verificados; endpoint OK local y vía túnel ngrok
  (`https://<sub>.ngrok-free.dev/mcp`).
- [2026-06-20] Logging: creado `app/logging_config.py` (`setup_logging`/`get_logger`,
  logger `app.*` a stdout, formato `fecha nivel [módulo] msg`). Agregado `LOG_LEVEL`
  a `app/config.py` y `.env.example`; sección "Logs / debugging" + fila en la tabla
  de env vars del `README.md`.
- [2026-06-20] Logging en `app/dataset.py` (cada HTTP GET en DEBUG; errores con
  detalle real en WARNING/ERROR) y en `app/server.py` (entrada, resultado y
  validaciones fallidas de cada tool).
- [2026-06-20] **Fix bug**: el logging reveló que con `stateless_http=True` el
  lifespan corre por request, redescargando `metadata.json` en cada llamada.
  Corregido en `app/dataset.py` (`load_metadata()` idempotente con cliente propio de
  corta vida; cliente global perezoso vía `_get_client()`, reutilizado entre
  requests; helper `_fetch_text(client, path)`) y `app/server.py` (carga de metadata
  movida a `__main__` con `asyncio.run` antes de `mcp.run()`; lifespan reducido a una
  llamada idempotente como red de seguridad, sin recrear/cerrar cliente por request).
  Verificado: 1 sola carga de metadata al arrancar y 0 redescargas tras 8 requests.
