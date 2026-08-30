"""CRUD de las tablas de catálogo.

Las ocho comparten exactamente la misma forma, así que se generan con una
fábrica en lugar de repetir ocho veces el mismo bloque de endpoints.
"""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import crud, schemas
from ..db import obtener_db
from ..security import exigir_api_key


def crear_router(
    *,
    tabla: str,
    etiqueta: str,
    Salida: type,
    Crear: type,
    Editar: type,
    tipo_id: type = int,
) -> APIRouter:
    router = APIRouter(prefix=f"/{tabla}", tags=[etiqueta])

    # `Ident` se evalúa al definir la función, así que FastAPI ve el tipo real
    # (int o str) y lo documenta correctamente en Swagger.
    Ident = tipo_id

    @router.get("", response_model=list[Salida], summary=f"Listar {tabla}")
    def listar(
        q: str | None = Query(None, description="Filtro por texto"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        conn: sqlite3.Connection = Depends(obtener_db),
    ) -> Any:
        return crud.listar(conn, tabla, limit=limit, offset=offset, q=q)

    @router.get("/{id_}", response_model=Salida, summary=f"Obtener un registro de {tabla}")
    def obtener(
        id_: Ident, conn: sqlite3.Connection = Depends(obtener_db)
    ) -> Any:
        registro = crud.obtener(conn, tabla, id_)
        if registro is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe {tabla}/{id_}.")
        return registro

    @router.post(
        "",
        response_model=Salida,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(exigir_api_key)],
        summary=f"Crear en {tabla}",
    )
    def crear(datos: Crear, conn: sqlite3.Connection = Depends(obtener_db)) -> Any:
        return crud.crear(conn, tabla, datos.model_dump())

    @router.patch(
        "/{id_}",
        response_model=Salida,
        dependencies=[Depends(exigir_api_key)],
        summary=f"Editar en {tabla}",
    )
    def editar(
        id_: Ident, datos: Editar, conn: sqlite3.Connection = Depends(obtener_db)
    ) -> Any:
        cambios = datos.model_dump(exclude_unset=True)
        registro = crud.actualizar(conn, tabla, id_, cambios)
        if registro is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe {tabla}/{id_}.")
        return registro

    @router.delete(
        "/{id_}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(exigir_api_key)],
        summary=f"Borrar en {tabla}",
    )
    def borrar(id_: Ident, conn: sqlite3.Connection = Depends(obtener_db)) -> None:
        if not crud.borrar(conn, tabla, id_):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe {tabla}/{id_}.")

    return router


ROUTERS = [
    crear_router(
        tabla="paises", etiqueta="catálogos", tipo_id=str,
        Salida=schemas.Pais, Crear=schemas.PaisCrear, Editar=schemas.PaisEditar,
    ),
    crear_router(
        tabla="dewey", etiqueta="catálogos", tipo_id=str,
        Salida=schemas.Dewey, Crear=schemas.DeweyCrear, Editar=schemas.DeweyEditar,
    ),
    crear_router(
        tabla="generos", etiqueta="catálogos",
        Salida=schemas.Genero, Crear=schemas.GeneroCrear, Editar=schemas.GeneroEditar,
    ),
    crear_router(
        tabla="autores", etiqueta="catálogos",
        Salida=schemas.Autor, Crear=schemas.AutorCrear, Editar=schemas.AutorEditar,
    ),
    crear_router(
        tabla="editoriales", etiqueta="catálogos",
        Salida=schemas.Editorial, Crear=schemas.EditorialCrear, Editar=schemas.EditorialEditar,
    ),
    crear_router(
        tabla="ubicaciones", etiqueta="catálogos",
        Salida=schemas.Ubicacion, Crear=schemas.UbicacionCrear, Editar=schemas.UbicacionEditar,
    ),
    crear_router(
        tabla="estanterias", etiqueta="mobiliario",
        Salida=schemas.Estanteria, Crear=schemas.EstanteriaCrear, Editar=schemas.EstanteriaEditar,
    ),
    # `modulos` no tiene ninguna columna de texto, así que su `q` no filtra
    # nada; se deja por uniformidad con el resto de listados.
    crear_router(
        tabla="modulos", etiqueta="mobiliario",
        Salida=schemas.Modulo, Crear=schemas.ModuloCrear, Editar=schemas.ModuloEditar,
    ),
]
