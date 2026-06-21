"""Configuración del servidor leída desde variables de entorno.

Todos los parámetros tienen un default razonable para poder correr el servidor
sin configuración previa. No hay secretos: el dataset es público.
"""

import os

# URL base por defecto del dataset (sin barra final).
_DEFAULT_DATASET_BASE_URL = (
	"https://raw.githubusercontent.com/maximilianozurita/arg-financial-data/main"
)

# Interfaz donde escucha el servidor. 0.0.0.0 es necesario dentro de un
# contenedor para que el servicio sea alcanzable desde afuera.
HOST: str = os.getenv("HOST", "0.0.0.0")

# Puerto configurable; default 8000.
PORT: int = int(os.getenv("PORT", "8000"))

# URL base del dataset configurable; se normaliza quitando la barra final
# para poder concatenar rutas sin ambigüedad.
DATASET_BASE_URL: str = os.getenv(
	"DATASET_BASE_URL", _DEFAULT_DATASET_BASE_URL
).rstrip("/")

# Nivel de logging (DEBUG, INFO, WARNING, ERROR). Default INFO.
# Usá DEBUG para ver cada descarga HTTP en detalle.
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
