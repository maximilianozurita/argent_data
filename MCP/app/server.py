"""Servidor MCP de datos económicos argentinos.

Expone tres tools de responsabilidad única sobre un dataset público:
  1. list_series        -> catálogo de series disponibles (el "menú").
  2. get_latest_value   -> último valor de una serie.
  3. get_series_data    -> serie histórica filtrada por rango de fechas.

Transporte: streamable-http (la forma HTTP vigente del SDK de MCP), porque el
servidor lo consume un agente remoto vía URL. El endpoint queda en
`http://HOST:PORT/mcp`.

Ejecutar:  python -m app.server
"""

from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from . import config, dataset
from .dataset import METADATA, DatasetError
from .logging_config import get_logger, setup_logging

# Configura el logging del proyecto apenas se importa el módulo, para que tanto
# el arranque como las tools queden registrados.
setup_logging()
logger = get_logger("server")


# --------------------------------------------------------------------------- #
# Ciclo de vida: descargar metadata UNA vez al arrancar, cerrar el cliente al
# apagar. Cumple "Al arrancar, descargá metadata.json UNA vez y mantené en
# memoria un mapa slug -> ...".
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(_server: FastMCP):
	# Red de seguridad: si la app se monta como ASGI (sin pasar por __main__),
	# garantizamos que la metadata esté cargada. load_metadata() es idempotente
	# (no redescarga si ya está en memoria), por eso es seguro aunque en modo
	# stateless este lifespan se ejecute por request.
	await dataset.load_metadata()
	yield


mcp = FastMCP(
	"arg-financial-data",
	host=config.HOST,
	port=config.PORT,
	# Modo sin estado + respuesta JSON: ideal para un agente remoto que abre
	# una conexión por llamada a través de un túnel (no requiere mantener
	# sesión/stream persistente).
	stateless_http=True,
	json_response=True,
	lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Helpers de validación
# --------------------------------------------------------------------------- #
def _require_slug(slug: str) -> dict[str, Any]:
	"""Devuelve la info de la serie o levanta un error legible si no existe."""
	if not isinstance(slug, str) or not slug.strip():
		logger.warning("Validación: slug vacío o de tipo inválido (%r)", slug)
		raise ToolError("El parámetro 'slug' es obligatorio.")
	info = METADATA.get(slug)
	if info is None:
		logger.warning("Validación: slug inexistente '%s'", slug)
		raise ToolError(
			f"No existe ninguna serie con slug '{slug}'. "
			f"Usá list_series() para ver los slugs disponibles."
		)
	return info


def _parse_date(value: str, nombre_param: str) -> date:
	"""Valida y parsea una fecha YYYY-MM-DD."""
	if not isinstance(value, str) or not value.strip():
		logger.warning("Validación: '%s' vacío o inválido (%r)", nombre_param, value)
		raise ToolError(f"El parámetro '{nombre_param}' es obligatorio (YYYY-MM-DD).")
	try:
		return datetime.strptime(value.strip(), "%Y-%m-%d").date()
	except ValueError:
		logger.warning("Validación: fecha inválida en '%s' (%r)", nombre_param, value)
		raise ToolError(
			f"La fecha '{value}' en '{nombre_param}' no es válida. "
			f"Usá el formato YYYY-MM-DD (ej: 2024-01-31)."
		)


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_series() -> list[dict[str, Any]]:
	"""Lista el catálogo completo de series económicas argentinas disponibles.

	Usala PRIMERO, cuando no sabés qué se puede consultar o necesitás el slug
	exacto de una serie. Es el "menú" del dataset y no hace ninguna descarga
	(lee del catálogo cargado en memoria).

	Devuelve una lista de series; cada una incluye:
	  - nombre:      nombre legible (ej: "Dólar Blue (Venta)").
	  - slug:        identificador para usar en las otras tools.
	  - categoria:   grupo temático (ej: "cambiario", "precios").
	  - unidad:      unidad de medida (ej: "ARS/USD", "índice").
	  - frecuencia:  frecuencia de actualización (ej: "diaria", "mensual").
	  - descripcion: descripción de la serie (puede estar vacía).
	"""
	logger.info("tool=list_series llamada")
	resultado = [
		{
			"nombre": info["nombre"],
			"slug": slug,
			"categoria": info["categoria"],
			"unidad": info["unidad"],
			"frecuencia": info["frecuencia"],
			"descripcion": info["descripcion"],
		}
		for slug, info in METADATA.items()
	]
	logger.info("tool=list_series ok -> %d series", len(resultado))
	return resultado


@mcp.tool()
async def get_latest_value(slug: str) -> dict[str, Any]:
	"""Devuelve el último valor publicado de una serie.

	Usala cuando querés el dato más reciente de una serie (ej: "¿a cuánto está
	hoy el dólar blue?"). Para series históricas o rangos de fechas usá
	get_series_data.

	Parámetros:
	  - slug: identificador de la serie (obtenelo de list_series).

	Devuelve un objeto con:
	  - slug, nombre: identificación de la serie.
	  - valor:        último valor numérico publicado.
	  - unidad:       unidad de medida del valor.
	  - fecha:        fecha (YYYY-MM-DD) a la que corresponde el valor.

	Errores: si el slug no existe o hay un fallo de red, devuelve un error
	legible.
	"""
	logger.info("tool=get_latest_value slug=%s", slug)
	info = _require_slug(slug)

	try:
		latest = await dataset.fetch_latest()
	except DatasetError as exc:
		logger.error("tool=get_latest_value slug=%s error: %s", slug, exc)
		raise ToolError(str(exc))

	entrada = next((item for item in latest if item.get("slug") == slug), None)
	if entrada is None or entrada.get("ultimo_valor") is None:
		logger.warning("tool=get_latest_value slug=%s sin último valor publicado", slug)
		raise ToolError(f"No hay un último valor publicado para la serie '{slug}'.")

	logger.info(
		"tool=get_latest_value slug=%s ok -> valor=%s fecha=%s",
		slug,
		entrada.get("ultimo_valor"),
		entrada.get("ultima_fecha"),
	)
	return {
		"slug": slug,
		"nombre": info["nombre"],
		"valor": entrada.get("ultimo_valor"),
		"unidad": info["unidad"],
		"fecha": entrada.get("ultima_fecha"),
	}


@mcp.tool()
async def get_series_data(slug: str, desde: str, hasta: str) -> dict[str, Any]:
	"""Devuelve la serie histórica de una serie filtrada por rango de fechas.

	Usala cuando necesitás la evolución de una serie en el tiempo o los valores
	entre dos fechas (ej: "dame el dólar blue de enero 2024", "evolución de la
	inflación en 2023"). Para un único valor reciente usá get_latest_value.

	Parámetros:
	  - slug:  identificador de la serie (obtenelo de list_series).
	  - desde: fecha de inicio del rango, inclusive, en formato YYYY-MM-DD.
	  - hasta: fecha de fin del rango, inclusive, en formato YYYY-MM-DD.

	Devuelve un objeto con:
	  - slug, nombre, unidad: identificación de la serie.
	  - desde, hasta:         rango solicitado.
	  - cantidad:             número de puntos devueltos.
	  - puntos:               lista de {fecha, valor} ordenada por fecha,
							  solo dentro del rango [desde, hasta].

	Errores: si el slug no existe, las fechas son inválidas, el rango está
	invertido, o no hay datos en el rango, devuelve un error legible.
	"""
	logger.info("tool=get_series_data slug=%s desde=%s hasta=%s", slug, desde, hasta)
	info = _require_slug(slug)
	d_desde = _parse_date(desde, "desde")
	d_hasta = _parse_date(hasta, "hasta")
	if d_desde > d_hasta:
		logger.warning(
			"tool=get_series_data slug=%s rango invertido (desde=%s > hasta=%s)",
			slug, desde, hasta,
		)
		raise ToolError(
			f"El rango es inválido: 'desde' ({desde}) es posterior a "
			f"'hasta' ({hasta})."
		)

	categoria = info["categoria"]
	try:
		raw_csv = await dataset.fetch_csv(categoria, slug)
	except DatasetError as exc:
		logger.error("tool=get_series_data slug=%s error: %s", slug, exc)
		raise ToolError(str(exc))

	puntos: list[dict[str, Any]] = []
	reader = csv.DictReader(io.StringIO(raw_csv))
	for fila in reader:
		fecha_str = (fila.get("fecha") or "").strip()
		valor_str = (fila.get("valor") or "").strip()
		if not fecha_str or not valor_str:
			continue
		try:
			fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
		except ValueError:
			continue  # fila con fecha malformada: la ignoramos
		if d_desde <= fecha <= d_hasta:
			try:
				valor: Any = float(valor_str)
			except ValueError:
				valor = valor_str  # valor no numérico: lo devolvemos tal cual
			puntos.append({"fecha": fecha_str, "valor": valor})

	if not puntos:
		logger.warning(
			"tool=get_series_data slug=%s sin datos entre %s y %s", slug, desde, hasta
		)
		raise ToolError(
			f"La serie '{slug}' no tiene datos entre {desde} y {hasta}."
		)

	puntos.sort(key=lambda p: p["fecha"])
	logger.info(
		"tool=get_series_data slug=%s ok -> %d puntos", slug, len(puntos)
	)
	return {
		"slug": slug,
		"nombre": info["nombre"],
		"unidad": info["unidad"],
		"desde": desde,
		"hasta": hasta,
		"cantidad": len(puntos),
		"puntos": puntos,
	}


if __name__ == "__main__":
	import asyncio

	logger.info(
		"Arrancando servidor MCP (dataset=%s, log_level=%s)",
		config.DATASET_BASE_URL,
		config.LOG_LEVEL,
	)
	# Descarga metadata UNA sola vez al arrancar, antes de aceptar requests.
	asyncio.run(dataset.load_metadata())
	# Transporte HTTP vigente del SDK de MCP. El endpoint queda en /mcp.
	mcp.run(transport="streamable-http")
