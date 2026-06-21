"""Configuración centralizada de logging.

Se usa un logger raíz propio del proyecto ("app") con su propio handler a
stdout, para no interferir con el logging de uvicorn/starlette. Todos los
módulos usan loggers hijos (`logging.getLogger("app.<modulo>")`) que propagan
hacia este handler.

Los logs van a stdout para que aparezcan en `docker compose logs`.
"""

from __future__ import annotations

import logging
import sys

from . import config

# Nombre del logger raíz del proyecto. Los módulos hacen
# logging.getLogger("app.server"), "app.dataset", etc.
ROOT_LOGGER_NAME = "app"


def setup_logging() -> None:
	"""Configura el logger raíz del proyecto. Idempotente."""
	level = getattr(logging, config.LOG_LEVEL, logging.INFO)

	logger = logging.getLogger(ROOT_LOGGER_NAME)
	logger.setLevel(level)
	# Evita duplicar handlers si se llama más de una vez.
	logger.handlers.clear()

	handler = logging.StreamHandler(sys.stdout)
	handler.setFormatter(
		logging.Formatter(
			fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
			datefmt="%Y-%m-%d %H:%M:%S",
		)
	)
	logger.addHandler(handler)
	# No propagar al root global para no duplicar con la config de uvicorn.
	logger.propagate = False


def get_logger(name: str) -> logging.Logger:
	"""Devuelve un logger hijo del logger raíz del proyecto."""
	return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
