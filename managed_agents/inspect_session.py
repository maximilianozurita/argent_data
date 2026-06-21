#!/usr/bin/env python3
"""Inspecciona una sesión por API (sin necesidad de la Consola web).

Uso:
  python inspect_session.py sesn_01Uv3837JFJaS98NUUwkmUFU

Muestra el estado y el uso de la sesión, y recorre todos los eventos: texto del
agente, llamadas a tools del MCP con sus inputs, y los resultados de esas tools.
Útil cuando no tenés acceso a la Consola de la organización de la API key.
"""

import json
import sys

from dotenv import load_dotenv

load_dotenv()

import anthropic


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Uso: python inspect_session.py <session_id>")
    session_id = sys.argv[1]

    client = anthropic.Anthropic()

    # Estado y uso de la sesión.
    session = client.beta.sessions.retrieve(session_id)
    print(f"sesión:  {session.id}")
    print(f"estado:  {session.status}")
    print(f"uso:     {getattr(session, 'usage', None)}")
    print("-" * 70)

    # Todos los eventos (transcripción completa: equivale a lo que ves en la Consola).
    for ev in client.beta.sessions.events.list(session_id=session_id):
        t = ev.type

        if t == "agent.message":
            for block in getattr(ev, "content", []) or []:
                if getattr(block, "type", None) == "text":
                    print(f"[agente] {block.text}")

        elif t == "agent.mcp_tool_use":
            inp = getattr(ev, "input", None)
            print(f"[MCP tool ->] {getattr(ev, 'name', '?')}  input={json.dumps(inp, ensure_ascii=False)}")

        elif t == "agent.mcp_tool_result":
            # El contenido del resultado puede ser texto o estructura; lo mostramos crudo.
            print(f"[MCP result <-] {getattr(ev, 'content', ev)}")

        elif t == "agent.tool_use":
            print(f"[tool built-in] {getattr(ev, 'name', '?')}")

        elif t == "session.error":
            print(f"[ERROR] {getattr(ev, 'error', ev)}")

        elif t.startswith("session.status_"):
            stop = getattr(ev, "stop_reason", None)
            extra = f"  stop_reason={getattr(stop, 'type', None)}" if stop else ""
            print(f"[estado] {t}{extra}")


if __name__ == "__main__":
    main()
