"""Configuración leída del entorno."""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Ruta al contenedor GeoPackage. Se puede apuntar a una copia para pruebas.
GPKG_PATH = Path(os.environ.get("BIBLIOTECA_GPKG", RAIZ / "sql" / "gpkg" / "biblioteca.gpkg"))

# Clave exigida en la cabecera X-API-Key para cualquier escritura.
# Si no está definida, la API arranca en solo lectura (ver api/security.py).
API_KEY = os.environ.get("BIBLIOTECA_API_KEY") or None

# Segundos de espera entre consultas a las APIs públicas durante una importación.
PAUSA_ENTRE_CONSULTAS = float(os.environ.get("BIBLIOTECA_PAUSA_LOTE", "0.5"))

TIMEOUT_HTTP = 10.0
