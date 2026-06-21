#!/usr/bin/env python3
"""Orquestador de Claude Managed Agents (beta) + servidor MCP de datos económicos.

Flujo:
  1. Crea (o reusa) un agente conectado a un servidor MCP referenciado por URL.
  2. Crea (o reusa) un environment con networking restringido al MCP.
  3. Crea una sesión que referencia el agente + el environment.
  4. Toma la pregunta del usuario (argumento de línea de comandos o input()).
  5. Abre el stream, manda la pregunta y va mostrando la respuesta del agente,
	 anunciando qué tool usa en cada paso, hasta que la sesión queda idle.

El servidor MCP es una pieza SEPARADA: tiene que estar levantado y expuesto por
URL pública (variable de entorno MCP_URL) ANTES de correr este script.

Uso:
  python orchestrator.py "¿Cuál es el último valor del dólar oficial?"
  python orchestrator.py              # pide la pregunta por input()
  python orchestrator.py --reset ...  # borra .agent_config.json y recrea todo
"""

import json
import os
import sys

# load_dotenv() tiene que correr ANTES de leer cualquier variable de entorno,
# o el .env no se carga a tiempo.
from dotenv import load_dotenv

load_dotenv()

import anthropic

# --------------------------------------------------------------------------- #
# Configuración (constantes fáciles de cambiar)
# --------------------------------------------------------------------------- #

# Modelo del agente. Configurable por entorno (AGENT_MODEL); por defecto un
# modelo eficiente tipo Haiku. Útil para subir a un modelo más capaz sin tocar
# el código (p. ej. AGENT_MODEL=claude-opus-4-8).
MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5")

# Archivo con el prompt de sistema (en español).
SYSTEM_PROMPT_PATH = "system_prompt.txt"

# Estado local: guarda los IDs del agente y el environment para reusarlos.
# Está en .gitignore. Borralo (o usá --reset) para forzar la recreación.
CONFIG_FILE = ".agent_config.json"

# Nombres de los recursos en la consola de Anthropic.
AGENT_NAME = "arg-econ-data-agent"
ENV_NAME = "arg-econ-data-env"

# Nombre lógico del servidor MCP; lo referencia el mcp_toolset del agente.
MCP_SERVER_NAME = "arg-data"

# ID de la skill custom (lo devuelve register_skill.py). Opcional: si está
# seteado, se adjunta al agente. Vive en .env (no se versiona). Sin él, el
# agente funciona igual, solo que sin la skill 'snapshot-cambiario'.
SKILL_ID = os.environ.get("SKILL_ID")

# Política de networking del sandbox:
#   "limited"      -> egress restringido salvo el MCP del agente (recomendado).
#   "unrestricted" -> egress completo.
# GOTCHA: con "limited" SIN allow_mcp_servers, las tools del MCP fallan EN
# SILENCIO (sin excepción): el agente simplemente no recibe datos.
NETWORKING_MODE = "limited"

# Plantilla de la URL de consola para ver la sesión en vivo.
CONSOLE_URL = "https://platform.claude.com/workspaces/default/sessions/{sid}"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def require_env(name: str) -> str:
	"""Devuelve la variable de entorno o sale con un mensaje claro si falta."""
	value = os.environ.get(name)
	if not value:
		sys.exit(
			f"Falta la variable de entorno {name}. "
			f"Copiá .env.example a .env y completá los valores "
			f"(ANTHROPIC_API_KEY y MCP_URL)."
		)
	return value


def read_system_prompt() -> str:
	"""Lee el prompt de sistema desde el archivo; error claro si no existe."""
	try:
		with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
			return f.read()
	except FileNotFoundError:
		sys.exit(
			f"No se encontró {SYSTEM_PROMPT_PATH}. "
			f"Debe estar en el directorio desde el que corrés el script."
		)


def load_config() -> dict:
	"""Lee .agent_config.json si existe; si no, devuelve {}."""
	try:
		with open(CONFIG_FILE, "r", encoding="utf-8") as f:
			return json.load(f)
	except (FileNotFoundError, json.JSONDecodeError):
		return {}


def save_config(config: dict) -> None:
	"""Persiste los IDs del agente y el environment."""
	with open(CONFIG_FILE, "w", encoding="utf-8") as f:
		json.dump(config, f, indent=2)


def networking_config(mode: str) -> dict:
	"""Traduce NETWORKING_MODE a la config de networking del environment."""
	if mode == "unrestricted":
		return {"type": "unrestricted"}
	# "limited": deny-by-default, pero habilitando los MCP del agente.
	return {"type": "limited", "allow_mcp_servers": True}


# --------------------------------------------------------------------------- #
# Crear o reusar agente + environment
# --------------------------------------------------------------------------- #

def get_or_create_resources(client, mcp_url: str, system_prompt: str, reset: bool) -> dict:
	"""Devuelve {agent_id, environment_id}, creándolos solo si hace falta.

	Patrón "crear una vez, reusar por ID": la primera corrida crea el agente y
	el environment y guarda sus IDs en .agent_config.json. Las corridas
	siguientes leen los IDs y van directo a la sesión, sin volver a crear.
	--reset borra el archivo para recrear desde cero (p. ej. si cambió el
	system prompt o el modelo).
	"""
	if reset and os.path.exists(CONFIG_FILE):
		os.remove(CONFIG_FILE)
		print(f"[reset] {CONFIG_FILE} borrado; se recrearán agente y environment.")

	config = load_config()
	if config.get("agent_id") and config.get("environment_id"):
		print(f"[reuso] agente {config['agent_id']} / environment {config['environment_id']}")
		return config

	# No hay config previa: crear el agente.
	# IMPORTANTE: model / system / tools / mcp_servers van en el AGENTE,
	# nunca en la sesión.
	print("[setup] creando agente...")
	# model / system / tools / mcp_servers van en el AGENTE.
	# always_allow: el MCP es de solo lectura, así que sus tools se ejecutan
	# automáticamente sin pedir confirmación en cada llamada.
	tools = [
		{
			"type": "mcp_toolset",
			"mcp_server_name": MCP_SERVER_NAME,
			"default_config": {
				"enabled": True,
				"permission_policy": {"type": "always_allow"},
			},
		},
	]

	agent_kwargs = dict(
		name=AGENT_NAME,
		model=MODEL,
		system=system_prompt,
		# El agente declara el servidor MCP por URL (sin auth: MCP público).
		mcp_servers=[{"type": "url", "name": MCP_SERVER_NAME, "url": mcp_url}],
		tools=tools,
	)

	# Skill custom opcional. La skill se carga dentro del contenedor mediante
	# progressive disclosure: el agente lee el SKILL.md sólo cuando aplica. Para
	# poder leerlo necesita el agent_toolset (read/bash), así que lo sumamos
	# únicamente cuando hay una skill que adjuntar.
	if SKILL_ID:
		tools.append({"type": "agent_toolset_20260401"})
		agent_kwargs["skills"] = [
			{"type": "custom", "skill_id": SKILL_ID, "version": "latest"},
		]

	agent = client.beta.agents.create(**agent_kwargs)

	print("[setup] creando environment...")
	environment = client.beta.environments.create(
		name=ENV_NAME,
		config={"type": "cloud", "networking": networking_config(NETWORKING_MODE)},
	)

	config = {"agent_id": agent.id, "environment_id": environment.id}
	save_config(config)
	print(f"[setup] guardado en {CONFIG_FILE}: {config}")
	return config


# --------------------------------------------------------------------------- #
# Loop de conversación (stream-first)
# --------------------------------------------------------------------------- #

def run_turn(client, session_id: str, question: str) -> str:
	"""Manda una pregunta y procesa el stream de eventos hasta que la sesión
	queda idle (o terminated). Devuelve el motivo de corte:
	"idle"        -> el agente terminó el turno (puede haber pedido aclaración).
	"terminated"  -> la sesión terminó (estado irreversible).
	"error"       -> hubo un session.error.
	"""
	# STREAM-FIRST: abrir el stream ANTES de mandar el mensaje, o se pierden los
	# primeros eventos.
	with client.beta.sessions.events.stream(session_id=session_id) as stream:
		client.beta.sessions.events.send(
			session_id=session_id,
			events=[{"type": "user.message", "content": [{"type": "text", "text": question}]}],
		)

		for event in stream:
			etype = event.type

			if etype == "agent.message":
				# Texto del agente: imprimir a medida que llega.
				for block in getattr(event, "content", []) or []:
					if getattr(block, "type", None) == "text":
						print(block.text, end="", flush=True)

			elif etype == "agent.mcp_tool_use":
				# Visibilidad de tools del MCP (clave para la demo).
				print(f"\n  [MCP tool: {getattr(event, 'name', '?')}]", flush=True)

			elif etype == "agent.tool_use":
				# Tool del toolset built-in (defensivo: no debería aparecer acá).
				print(f"\n  [tool built-in: {getattr(event, 'name', '?')}]", flush=True)

			elif etype == "session.error":
				err = getattr(event, "error", event)
				print(f"\n[ERROR de sesión: {err}]", file=sys.stderr, flush=True)
				return "error"

			elif etype == "session.status_terminated":
				return "terminated"

			elif etype == "session.status_idle":
				stop = getattr(event, "stop_reason", None)
				if stop is not None and getattr(stop, "type", None) == "requires_action":
					# El agente pidió permiso para ejecutar una tool. Las tools de
					# un MCP externo pueden requerir confirmación del cliente; como
					# este MCP es un proveedor de datos de SOLO LECTURA, autorizamos
					# automáticamente todas las pendientes y seguimos el stream.
					pending_ids = getattr(stop, "event_ids", None) or []
					for eid in pending_ids:
						print(f"  [permiso] autorizando tool ({eid})", flush=True)
						client.beta.sessions.events.send(
							session_id=session_id,
							events=[{
								"type": "user.tool_confirmation",
								"tool_use_id": eid,
								"result": "allow",
							}],
						)
					continue
				return "idle"

	return "idle"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
	# Parseo simple de args: --reset (flag) + primer posicional = pregunta.
	args = sys.argv[1:]
	reset = "--reset" in args
	args = [a for a in args if a != "--reset"]
	cli_question = args[0] if args else None

	api_key = require_env("ANTHROPIC_API_KEY")  # validación temprana (el SDK la relee)
	mcp_url = require_env("MCP_URL")
	system_prompt = read_system_prompt()

	client = anthropic.Anthropic()

	# Chequeo de versión del SDK: la superficie beta tiene que existir.
	if not hasattr(client.beta, "agents"):
		sys.exit(
			"Tu versión de 'anthropic' no expone client.beta.agents (Managed Agents). "
			"Actualizá: pip install -U anthropic"
		)

	try:
		config = get_or_create_resources(client, mcp_url, system_prompt, reset)

		session = client.beta.sessions.create(
			agent=config["agent_id"],
			environment_id=config["environment_id"],
		)
		print(f"[sesión] {session.id}")
		print(f"[en vivo] {CONSOLE_URL.format(sid=session.id)}\n")

		# Primer turno: pregunta de CLI o por input().
		if cli_question:
			question = cli_question
		else:
			question = input("Pregunta: ").strip()

		# Loop de turnos: tras cada idle se puede mandar un follow-up (útil para
		# responder cuando el agente pregunta "¿cuál serie?"). Vacío / exit / EOF
		# termina.
		while question:
			print(f"\n> {question}\n")
			reason = run_turn(client, session.id, question)
			print()  # newline tras el texto del turno
			if reason in ("terminated", "error"):
				break
			try:
				question = input("\nFollow-up (Enter o 'exit' para salir): ").strip()
			except EOFError:
				break
			if question.lower() == "exit":
				break

	except anthropic.AuthenticationError:
		sys.exit("Error de autenticación: revisá ANTHROPIC_API_KEY.")
	except anthropic.NotFoundError as e:
		sys.exit(
			f"Recurso no encontrado ({e}). Quizá el agente/environment guardado "
			f"en {CONFIG_FILE} ya no existe. Probá con --reset."
		)
	except anthropic.APIConnectionError as e:
		sys.exit(f"Error de conexión con la API: {e}")
	except anthropic.APIStatusError as e:
		sys.exit(f"Error de la API ({e.status_code}): {e.message}")


if __name__ == "__main__":
	main()
