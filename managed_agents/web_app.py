#!/usr/bin/env python3
"""Backend web mínimo (Flask) para el chat con el agente Managed Agents + MCP.

Reusa la lógica de orchestrator.py (crear/reusar agente+environment, constantes,
helpers). El navegador habla SOLO con este backend; la ANTHROPIC_API_KEY nunca
sale del servidor.

Endpoints:
  GET  /              -> sirve la página de chat (templates/index.html)
  POST /api/session   -> crea una sesión nueva, devuelve {session_id, console_url}
  POST /api/chat      -> recibe {session_id, message}; abre el stream del agente,
                         manda el mensaje y reenvía los eventos al navegador como
                         SSE (text / tool / done / error). Autoriza tools del MCP
                         automáticamente (solo lectura).

Uso:
  python web_app.py          # http://127.0.0.1:5000

El servidor MCP debe estar levantado y expuesto por URL (MCP_URL) ANTES de correr.
"""

import json

from flask import Flask, Response, request, render_template

import anthropic
import orchestrator as orch  # al importar, orchestrator ya corre load_dotenv()

app = Flask(__name__)

# --- Setup único al arrancar (validación + crear/reusar agente y environment) ---
MCP_URL = orch.require_env("MCP_URL")
orch.require_env("ANTHROPIC_API_KEY")  # validación temprana (el SDK la relee)
SYSTEM_PROMPT = orch.read_system_prompt()

client = anthropic.Anthropic()
if not hasattr(client.beta, "agents"):
    raise SystemExit(
        "Tu versión de 'anthropic' no expone client.beta.agents (Managed Agents). "
        "Actualizá: pip install -U anthropic"
    )

# Reusa .agent_config.json si existe; si no, crea agente + environment una vez.
RESOURCES = orch.get_or_create_resources(client, MCP_URL, SYSTEM_PROMPT, reset=False)


def sse(obj: dict) -> str:
    """Serializa un evento como frame SSE."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/session")
def new_session():
    """Crea una sesión nueva (una por conversación) sobre el agente reusado."""
    session = client.beta.sessions.create(
        agent=RESOURCES["agent_id"],
        environment_id=RESOURCES["environment_id"],
    )
    return {
        "session_id": session.id,
        "console_url": orch.CONSOLE_URL.format(sid=session.id),
    }


@app.post("/api/chat")
def chat():
    """Manda un mensaje a la sesión y reenvía los eventos del agente como SSE."""
    data = request.get_json(force=True)
    session_id = data["session_id"]
    message = data["message"]

    def generate():
        try:
            # STREAM-FIRST: abrir el stream antes de mandar el mensaje.
            with client.beta.sessions.events.stream(session_id=session_id) as stream:
                client.beta.sessions.events.send(
                    session_id=session_id,
                    events=[{"type": "user.message",
                             "content": [{"type": "text", "text": message}]}],
                )
                for event in stream:
                    etype = event.type

                    if etype == "agent.message":
                        for block in getattr(event, "content", []) or []:
                            if getattr(block, "type", None) == "text":
                                yield sse({"type": "text", "text": block.text})

                    elif etype == "agent.mcp_tool_use":
                        yield sse({"type": "tool", "name": getattr(event, "name", "?")})

                    elif etype == "session.error":
                        yield sse({"type": "error",
                                   "message": str(getattr(event, "error", event))})
                        return

                    elif etype == "session.status_terminated":
                        yield sse({"type": "done"})
                        return

                    elif etype == "session.status_idle":
                        stop = getattr(event, "stop_reason", None)
                        if stop is not None and getattr(stop, "type", None) == "requires_action":
                            # MCP de solo lectura: autorizar las tools pendientes.
                            for eid in (getattr(stop, "event_ids", None) or []):
                                client.beta.sessions.events.send(
                                    session_id=session_id,
                                    events=[{"type": "user.tool_confirmation",
                                             "tool_use_id": eid, "result": "allow"}],
                                )
                            continue
                        yield sse({"type": "done"})
                        return
        except anthropic.APIStatusError as e:
            yield sse({"type": "error", "message": f"API ({e.status_code}): {e.message}"})
        except Exception as e:  # red de seguridad: que el front siempre cierre
            yield sse({"type": "error", "message": str(e)})

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # evita buffering en proxies
    }
    return Response(generate(), headers=headers)


if __name__ == "__main__":
    # threaded=True: permite atender el POST /api/session y el stream a la vez.
    # use_reloader=False: evita ejecutar el setup (crear/reusar agente) dos veces.
    app.run(host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
