"""Capa de acceso al dataset público de datos económicos argentinos.

Responsabilidades:
- Mantener un único cliente HTTP (httpx.AsyncClient) reutilizable entre requests.
- Descargar `metadata.json` UNA sola vez al arrancar y construir un mapa
  en memoria `slug -> {categoria, nombre, unidad, frecuencia, descripcion}`.
- Exponer helpers para descargar `latest.json` y los CSV por serie.

Todos los fallos de red/HTTP se traducen a `DatasetError` con un mensaje
legible, sin exponer detalles internos (tracebacks, URLs completas, etc.).

Nota sobre el ciclo de vida: en modo HTTP stateless el lifespan de la app
puede ejecutarse por request, por eso el cliente se crea de forma perezosa y
`load_metadata()` es idempotente (no redescarga si ya hay metadata en memoria).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from . import config
from .logging_config import get_logger

logger = get_logger("dataset")


class DatasetError(Exception):
	"""Error de acceso al dataset, con un mensaje seguro para el agente."""


# Cliente HTTP único para las descargas por request (latest.json, CSV). Se crea
# de forma perezosa en el event loop que atiende los requests y se reutiliza.
_client: httpx.AsyncClient | None = None

# Mapa en memoria slug -> info de la serie. Se llena en `load_metadata()`.
METADATA: dict[str, dict[str, Any]] = {}


def _new_client() -> httpx.AsyncClient:
	"""Construye un cliente httpx configurado contra la base del dataset."""
	return httpx.AsyncClient(
		base_url=config.DATASET_BASE_URL,
		timeout=httpx.Timeout(10.0),
		follow_redirects=True,
	)


def _get_client() -> httpx.AsyncClient:
	"""Devuelve el cliente global, creándolo de forma perezosa la primera vez."""
	global _client
	if _client is None:
		_client = _new_client()
	return _client


async def close_client() -> None:
	"""Cierra el cliente HTTP global (útil en un shutdown ordenado)."""
	global _client
	if _client is not None:
		await _client.aclose()
		_client = None


async def _fetch_text(client: httpx.AsyncClient, path: str) -> str:
	"""Descarga un recurso del dataset y devuelve su cuerpo como texto.

	Loguea la descarga y traduce cualquier fallo de red/HTTP a `DatasetError`
	legible (el detalle real queda solo en el log, no llega al agente).
	"""
	logger.debug("HTTP GET %s%s", config.DATASET_BASE_URL, path)
	try:
		response = await client.get(path)
		response.raise_for_status()
		logger.debug(
			"HTTP GET %s -> %s (%d bytes)",
			path, response.status_code, len(response.content),
		)
		return response.text
	except httpx.HTTPStatusError as exc:
		logger.warning("HTTP GET %s -> estado %s", path, exc.response.status_code)
		raise DatasetError(
			f"No se pudo obtener el recurso solicitado (estado "
			f"{exc.response.status_code}). Puede que la serie no tenga datos "
			f"publicados."
		) from exc
	except httpx.HTTPError as exc:  # timeouts, DNS, conexión, etc.
		logger.error("HTTP GET %s falló: %s: %s", path, type(exc).__name__, exc)
		raise DatasetError(
			"Fallo de red al consultar el dataset. Intentá nuevamente más tarde."
		) from exc


async def _get_text(path: str) -> str:
	"""Descarga un recurso usando el cliente global reutilizable."""
	return await _fetch_text(_get_client(), path)


async def load_metadata() -> None:
	"""Descarga `metadata.json` una vez y construye el mapa en memoria.

	Es idempotente: si la metadata ya está cargada, no hace nada (clave en modo
	stateless, donde el lifespan puede correr por request). Usa un cliente
	propio de corta vida para poder llamarse también desde el arranque
	(`asyncio.run`) sin acoplarse al cliente global.
	"""
	if METADATA:
		return

	async with _new_client() as client:
		raw = await _fetch_text(client, "/metadata.json")

	try:
		series = json.loads(raw)
	except json.JSONDecodeError as exc:
		raise DatasetError("El catálogo de series (metadata) está corrupto.") from exc

	mapa: dict[str, dict[str, Any]] = {}
	for serie in series:
		slug = serie.get("slug")
		if not slug:
			continue
		mapa[slug] = {
			"categoria": serie.get("categoria"),
			"nombre": serie.get("nombre"),
			"unidad": serie.get("unidad"),
			"frecuencia": serie.get("frecuencia"),
			"descripcion": serie.get("descripcion", ""),
		}

	if not mapa:
		raise DatasetError("El catálogo de series vino vacío.")

	METADATA.clear()
	METADATA.update(mapa)
	logger.info("Metadata cargada: %d series en memoria", len(METADATA))


async def fetch_latest() -> list[dict[str, Any]]:
	"""Descarga `latest.json` (último valor de cada serie)."""
	raw = await _get_text("/latest.json")
	try:
		return json.loads(raw)
	except json.JSONDecodeError as exc:
		raise DatasetError("Los últimos valores (latest) están corruptos.") from exc


async def fetch_csv(categoria: str, slug: str) -> str:
	"""Descarga el CSV histórico `data/{categoria}/{slug}.csv` como texto."""
	return await _get_text(f"/data/{categoria}/{slug}.csv")
