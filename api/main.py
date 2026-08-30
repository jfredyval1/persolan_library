"""API de la biblioteca personal.

Expone CRUD sobre el GeoPackage existente y da de alta libros a partir del ISBN.
El esquema SQL no se toca desde aquí: lo crean los scripts de sql/.
"""

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from .config import GOOGLE_API_KEY, GPKG_PATH
from .db import conectar
from .routers import catalogos, ejemplares, importar, isbn, libros
from .security import avisar_si_sin_clave

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("biblioteca")

DESCRIPCION = """
Catálogo de la biblioteca personal sobre un GeoPackage (SQLite).

**Atajo recomendado**: `POST /libros/desde-isbn` busca la ficha en Open Library
(o Google Books) y da de alta el libro creando de paso el autor y la editorial.
Para varios de golpe, `POST /importar/isbns`.

Las lecturas son abiertas; toda escritura exige la cabecera `X-API-Key`
(botón **Authorize** arriba a la derecha).
"""

@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    avisar_si_sin_clave()
    if GOOGLE_API_KEY is None:
        # Sin avisar, el respaldo falla en silencio: Open Library responde
        # primero y solo se nota cuando un ISBN que ella no conoce da error.
        log.warning(
            "GOOGLE_API_KEY no está definida: Google Books responderá 429 a todo "
            "(el uso anónimo tiene cuota 0). Open Library queda como única fuente."
        )
    conectar().close()  # falla pronto y con un mensaje claro si el .gpkg no está
    log.info("GeoPackage: %s", GPKG_PATH)
    yield


app = FastAPI(
    title="Biblioteca personal",
    description=DESCRIPCION,
    version="1.0.0",
    lifespan=ciclo_de_vida,
)

for router in catalogos.ROUTERS:
    app.include_router(router)
app.include_router(libros.router)
app.include_router(ejemplares.router)
app.include_router(isbn.router)
app.include_router(importar.router)


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/salud", tags=["estado"], summary="Comprobar la conexión con el GeoPackage")
def salud() -> dict:
    conn = conectar()
    try:
        tablas = {
            fila["table_name"]: fila["last_change"]
            for fila in conn.execute(
                "SELECT table_name, last_change FROM gpkg_contents ORDER BY table_name"
            )
        }
        total = conn.execute("SELECT COUNT(*) AS n FROM libros").fetchone()["n"]
    finally:
        conn.close()
    return {"gpkg": str(GPKG_PATH), "libros": total, "ultimo_cambio_por_tabla": tablas}


@app.exception_handler(sqlite3.IntegrityError)
def error_de_integridad(request: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
    """Traduce las restricciones del esquema a respuestas HTTP con sentido."""
    mensaje = str(exc)

    if "UNIQUE constraint failed" in mensaje:
        if "libros.isbn" in mensaje:
            detalle = "Ya existe un libro con ese ISBN."
        else:
            campo = mensaje.split("failed:")[-1].strip()
            detalle = f"Ya existe un registro con ese valor ({campo})."
        codigo = status.HTTP_409_CONFLICT
    elif "FOREIGN KEY constraint failed" in mensaje:
        detalle = (
            "Referencia inexistente: alguno de los ids enviados "
            "(editorial, autor, género, ubicación o libro) no está en la base."
        )
        codigo = status.HTTP_400_BAD_REQUEST
    elif "CHECK constraint failed" in mensaje:
        detalle = f"La fila incumple una regla del esquema: {mensaje}"
        codigo = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif "NOT NULL constraint failed" in mensaje:
        detalle = f"Falta un campo obligatorio: {mensaje.split('failed:')[-1].strip()}"
        codigo = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        detalle = mensaje
        codigo = status.HTTP_400_BAD_REQUEST

    return JSONResponse(status_code=codigo, content={"detail": detalle})


@app.exception_handler(sqlite3.OperationalError)
def error_operativo(request: Request, exc: sqlite3.OperationalError) -> JSONResponse:
    if "locked" in str(exc) or "busy" in str(exc):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "El GeoPackage está bloqueado por otro proceso. "
                "Cierra la edición en QGIS y reinténtalo."
            },
        )
    log.exception("Error operativo de SQLite")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
