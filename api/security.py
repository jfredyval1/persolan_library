"""Autenticación por clave de API.

SQLite no tiene usuarios ni roles: la única protección posible es de aplicación.
Se exige la clave solo en las escrituras; las lecturas quedan abiertas.
"""

import logging
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from .config import API_KEY

log = logging.getLogger("biblioteca")

# auto_error=False para poder dar un mensaje propio y para que Swagger UI
# muestre el botón "Authorize" sin bloquear las rutas de lectura.
_cabecera = APIKeyHeader(name="X-API-Key", auto_error=False)


def exigir_api_key(clave: str | None = Depends(_cabecera)) -> None:
    if API_KEY is None:
        # Mejor fallar visiblemente que quedar abierto por descuido.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "La API está en solo lectura: define BIBLIOTECA_API_KEY para poder escribir.",
        )
    if clave is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta la cabecera X-API-Key.")
    if not secrets.compare_digest(clave, API_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clave de API incorrecta.")


def avisar_si_sin_clave() -> None:
    if API_KEY is None:
        log.warning(
            "BIBLIOTECA_API_KEY no está definida: la API arranca en SOLO LECTURA. "
            "Toda escritura responderá 503."
        )
