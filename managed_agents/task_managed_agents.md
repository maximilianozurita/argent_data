## Descripción
Construí un script Python que use el SDK de Anthropic (Claude Managed Agents)
para crear un agente, conectarlo a un servidor MCP externo, mandarle una
pregunta del usuario y mostrar la respuesta en streaming.

IMPORTANTE: Managed Agents está en beta. Verificá en la documentación vigente
la sintaxis exacta de: crear un agente, referenciar un servidor MCP por URL en
la definición del agente, crear un environment, crear una sesión, y procesar el
stream de eventos. La API puede haber cambiado; usá la forma actual de la doc.

QUÉ TIENE QUE HACER EL SCRIPT
1. Crear (o reusar) un agente con:
   - modelo configurable (default: un modelo eficiente tipo Haiku; dejalo en una
     constante fácil de cambiar).
   - el prompt de sistema leído desde un archivo system_prompt.txt.
   - el servidor MCP referenciado por su URL pública (leída de variable de
     entorno MCP_URL).
   - si el SDK permite fijar temperatura baja para mayor determinismo, hacelo.
2. Crear un environment. Si es posible, restringí el networking del sandbox al
   dominio del MCP / del dataset; si no, dejalo configurable y documentado.
3. Crear una sesión que referencie el agente y el environment.
4. Tomar la pregunta del usuario como argumento de línea de comandos (o por
   input si no se pasa).
5. Abrir el stream, mandar la pregunta como evento de usuario, y procesar los
   eventos: ir mostrando el texto del agente y avisar qué tool usa en cada paso,
   hasta el evento de sesión idle. Mostrar el llamado de tools tiene que verse
   en la salida (es importante para la demo).

PROMPT DE SISTEMA (creá system_prompt.txt con este contenido, en español)
- El agente responde consultas sobre datos económicos y financieros de
  Argentina, usando EXCLUSIVAMENTE los datos que obtiene de las tools del MCP.
- Es un proveedor de DATOS, NO un asesor: nunca da recomendaciones de inversión
  ni opiniones sobre qué comprar o vender. Solo informa datos y los explica.
- Si no tiene datos para responder (serie inexistente, fuera de rango), lo dice
  claramente y, si sirve, ofrece listar las series disponibles. Nunca inventa
  números ni series.
- Ante ambigüedad (ej. "el dólar"), usa list_series para ver las opciones y o
  bien pregunta cuál, o asume la más común declarándolo explícitamente. Definí
  una regla fija para esto para que la misma pregunta dé siempre la misma
  respuesta.
- Incluye siempre la unidad y la fecha de los datos que reporta.
- Para preguntas que comparan o calculan (ej. variación porcentual), usa
  get_series_data, hace el cálculo de forma explícita y muestra cómo llegó al
  resultado.
- Formato de respuesta consistente y conciso.

CONFIG Y SEGURIDAD
- ANTHROPIC_API_KEY y MCP_URL se leen de variables de entorno, nunca
  hardcodeadas.
- .env.example SIN valores reales, con ANTHROPIC_API_KEY y MCP_URL.

ENTREGABLES
- El script orquestador, comentado.
- system_prompt.txt.
- requirements.txt (incluí anthropic).
- .env.example.
- README con cómo correrlo, aclarando que el MCP tiene que estar levantado y
  expuesto por URL ANTES de correr el script.
SETUP LOCAL (no Docker)
- El orquestador NO va en Docker: es un script efímero que se corre a mano,
  no un servicio. Documentá en el README el setup con virtualenv:
  crear el venv, activarlo, pip install -r requirements.txt, y correr el script.
- Aclará que el orquestador y el MCP son piezas separadas: el MCP corre como
  servicio (Docker + túnel) y debe estar arriba ANTES de correr el orquestador.

## Flujo de desarrollo:
Primero investiga todo lo necesario para la tarea, luego se arma un plan haciendo las preguntas pertinentes sobre la tecnologia a utilizar, el sistema de directorios, la arquitectura, etc. Si hay cambios en el plan se modifica este archivo y se van logueando las decisiones. Luego, cuando ya esta todo ok, se pregunta si ejecutar el plan para comenzar a realizar los cambios. Todo se va logueando en este archivo.

## Decisiones
<!-- Una subsección por cada decisión no trivial tomada durante el planning -->

### Decisión 1: Reuso del agente — "crear una vez, reusar por ID"
- **Elegida:** la primera corrida crea agente + environment y guarda sus IDs en
  `.agent_config.json` (gitignored). Las corridas siguientes leen los IDs y van
  directo a `sessions.create`. Flag `--reset` borra el archivo y recrea todo.
- **Descartadas:** crear un agente nuevo en cada corrida (anti-patrón de la doc:
  acumula agentes huérfanos y paga latencia de creación); detección automática de
  drift con `agents.update` (más compleja; se reemplaza por el flag `--reset`
  explícito).

### Decisión 2: Networking del sandbox
- **Elegida:** `limited` + `allow_mcp_servers: True` (egress restringido salvo el
  MCP del agente), configurable a `unrestricted` por la constante `NETWORKING_MODE`.
- **Descartadas:** `unrestricted` por defecto (sin restricción de red).

### Decisión 3: Regla ante ambigüedad (ej. "el dólar")
- **Elegida:** el agente usa `list_series` y, si hay varias series candidatas,
  **pregunta al usuario cuál** en vez de asumir. Determinista: la misma consulta
  ambigua produce siempre el mismo pedido de aclaración.
- **Descartadas:** asumir el dólar oficial (declarándolo); asumir el dólar blue.

### Decisión 4: Modelo, temperatura y tools
- **Modelo:** `claude-haiku-4-5` en constante `MODEL` fácil de cambiar.
- **Temperatura:** Managed Agents NO expone `temperature` en la config del agente
  (campos documentados: name/model/system/tools/mcp_servers/skills/description/
  multiagent/metadata). No se pasa; el determinismo se logra vía el system prompt.
- **Tools:** solo `mcp_toolset` (sin el toolset built-in de bash/archivos): el
  agente solo necesita las tools del MCP.

### Decisión 5: Carga de .env y estructura
- **`.env`:** se carga con `python-dotenv` (`load_dotenv()`) al inicio, antes de
  leer cualquier variable de entorno.
- **Estructura:** un único `orchestrator.py` (script efímero, no paquete).

## Casos de ejemplo
<!-- Sección donde se muestran casos de ejemplo -->

- `python orchestrator.py "¿Cuál es el último valor del dólar oficial?"`
  → el agente llama `list_series` / `get_latest_value` (se ve `[MCP tool: ...]`),
  responde con el valor, su unidad y la fecha.
- `python orchestrator.py "¿a cuánto está el dólar?"` (ambiguo)
  → el agente usa `list_series` y pregunta cuál serie (oficial/blue/MEP/...). En el
  follow-up se aclara y entrega el dato con unidad y fecha.
- `python orchestrator.py "variación del dólar oficial entre enero y junio de 2024"`
  → usa `get_series_data`, muestra valores de inicio/fin con fechas y el cálculo.
- `python orchestrator.py` (sin `.env` configurado)
  → falla con mensaje claro pidiendo completar ANTHROPIC_API_KEY / MCP_URL.

## Plan de implementación
<!-- Pasos concretos y ordenados. La ejecución los marca [x] al completar cada uno. Concentrarse en realizar una tarea a la vez -->
- [x] Paso 1: `.gitignore` (`.env`, `.agent_config.json`, `.venv`, `__pycache__`).
- [x] Paso 2: `requirements.txt` (`anthropic>=0.92.0`, `python-dotenv>=1.0.0`).
- [x] Paso 3: `.env.example` con `ANTHROPIC_API_KEY=` y `MCP_URL=` vacíos.
- [x] Paso 4: `system_prompt.txt` (español; regla fija "preguntar cuál").
- [x] Paso 5: `orchestrator.py` (constantes, helpers, crear-o-reusar + `--reset`,
      `sessions.create` + URL de consola, lectura de pregunta, loop stream-first
      con anuncio de tools y gate idle/terminated, errores tipados).
- [x] Paso 6: `README.md` (setup venv sin Docker; MCP arriba antes de correr).
- [x] Paso 7: completar este archivo (Decisiones / Plan / Log).
- [ ] Paso 8 (verificación end-to-end): requiere ANTHROPIC_API_KEY y un MCP real
      levantado y expuesto por URL — pendiente del usuario.

## Restricciones y gotchas
<!-- Lo no obvio que apareció en el planning y que la ejecución debe tener en cuenta.
     Este es el campo más valioso para una sesión fría. -->

- `load_dotenv()` debe correr ANTES de leer variables de entorno.
- `model`/`system`/`tools`/`mcp_servers` van en el AGENTE, nunca en la sesión (la
  sesión solo toma `agent` + `environment_id`).
- Stream-first: abrir `events.stream` ANTES de `events.send`, o se pierden eventos.
- Gate de fin: cortar en `session.status_terminated`; en `session.status_idle`
  cortar salvo `stop_reason.type == "requires_action"`.
- Networking `limited` SIN `allow_mcp_servers: True` → las tools del MCP fallan EN
  SILENCIO (sin excepción): si el agente "no trae datos" sin error, sospechar esto.
- Las tools del MCP disparan eventos `agent.mcp_tool_use` (con `.name`), distintos
  de `agent.tool_use` (toolset built-in). Se manejan ambos por las dudas.
- Managed Agents está en beta (`managed-agents-2026-04-01`, header puesto por el
  SDK). Si falta `client.beta.agents`, actualizar `anthropic`.
- Archive de agente/environment es permanente — para resetear, borrar
  `.agent_config.json` (o `--reset`), no archivar.
- El MCP de este demo se asume público (sin auth). Si necesitara auth, iría en un
  vault referenciado por `vault_ids` en la sesión (no implementado).

## Log de cambios
<!-- La execution session completa esta sección. Formato:
     - [fecha] Paso N: qué se cambió, en qué archivo, por qué, cada cambio en el codigo en esta sesion se debe registrar aca. Si se compacta mantener en contexto que se deben registar cambios aca -->
- [2026-06-20] Paso 1: creado `.gitignore` (ignora `.env`, `.agent_config.json`,
  `.venv/`, `__pycache__/`) — evitar commitear secretos y estado local.
- [2026-06-20] Paso 2: creado `requirements.txt` (`anthropic>=0.92.0`,
  `python-dotenv>=1.0.0`) — SDK con superficie Managed Agents + carga de `.env`.
- [2026-06-20] Paso 3: creado `.env.example` (ANTHROPIC_API_KEY, MCP_URL vacíos).
- [2026-06-20] Paso 4: creado `system_prompt.txt` (español) con el contenido del
  spec y la regla fija "preguntar cuál" ante ambigüedad.
- [2026-06-20] Paso 5: creado `orchestrator.py` — crear-o-reusar agente+environment
  vía `.agent_config.json` (+ `--reset`), `mcp_servers` por URL leída de `MCP_URL`,
  `tools=[mcp_toolset]`, environment con networking `limited`+`allow_mcp_servers`,
  sesión + URL de consola, loop stream-first con anuncio de `[MCP tool: ...]` y
  gate idle/terminated, validación de env vars y errores tipados del SDK.
- [2026-06-20] Paso 6: creado `README.md` (setup venv sin Docker; aclara que el MCP
  debe estar arriba y expuesto por URL antes de correr; reuso, --reset, networking).
- [2026-06-20] Paso 7: completadas las secciones Decisiones / Casos / Plan /
  Restricciones / Log de este archivo.
- [2026-06-20] Fix: en la primera prueba real la sesión quedó `idle` con
  `stop_reason=requires_action` tras llamar `list_series` (la tool del MCP externo
  requería confirmación del cliente y el loop solo hacía `continue`, colgándose).
  En `orchestrator.py` (`run_turn`) se agregó autoconfirmación: ante
  `requires_action` se mandan `user.tool_confirmation` con `result="allow"` para
  cada id en `stop_reason.event_ids` y se sigue el stream. Justificado: el MCP es
  proveedor de datos de solo lectura. También se creó `inspect_session.py` para
  inspeccionar sesiones por API (estado, uso y eventos) sin la Consola web.
- [2026-06-20] Fix: el MCP pedía confirmación en CADA tool (always_ask), generando
  spam de "[permiso] autorizando tool ...". En `orchestrator.py` se agregó
  `default_config: {enabled, permission_policy: always_allow}` al `mcp_toolset`
  para que las tools del MCP se ejecuten sin confirmación (requiere `--reset` para
  recrear el agente). Se dejó la autoconfirmación del loop como red de seguridad.
- [2026-06-20] Feature: frontend de chat con streaming. Se agregó `web_app.py`
  (backend Flask que reusa orchestrator.py: setup único de agente/environment,
  endpoints `POST /api/session` y `POST /api/chat` que reenvía los eventos del
  agente al navegador como SSE, autoconfirmando tools del MCP) y
  `templates/index.html` (UI de chat: respuesta en vivo + chips por tool, soporta
  follow-ups, botón "Nueva conversación"). `flask>=3.0.0` agregado a
  requirements.txt. La API key queda server-side. Smoke test OK: GET / y
  POST /api/session devuelven 200 reusando el agente existente.
