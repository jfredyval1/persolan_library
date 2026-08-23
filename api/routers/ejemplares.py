"""CRUD de ejemplares: las copias físicas de cada libro."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import crud
from ..db import obtener_db
from ..schemas import Ejemplar, EjemplarCrear, EjemplarEditar
from ..security import exigir_api_key

router = APIRouter(prefix="/ejemplares", tags=["ejemplares"])


@router.get("", response_model=list[Ejemplar], summary="Listar ejemplares")
def listar(
    q: str | None = Query(None, description="Filtro por notas o por a quién está prestado"),
    libro_id: int | None = None,
    ubicacion_id: int | None = None,
    en_prestamo: bool | None = Query(None, description="Filtrar por préstamo"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(obtener_db),
):
    return crud.listar(
        conn, "ejemplares",
        limit=limit, offset=offset, q=q,
        filtros={
            "libro_id": libro_id,
            "ubicacion_id": ubicacion_id,
            "en_prestamo": en_prestamo,
        },
    )


@router.get("/{ejemplar_id}", response_model=Ejemplar, summary="Obtener un ejemplar")
def obtener(ejemplar_id: int, conn: sqlite3.Connection = Depends(obtener_db)):
    ejemplar = crud.obtener(conn, "ejemplares", ejemplar_id)
    if ejemplar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe el ejemplar {ejemplar_id}.")
    return ejemplar


@router.post(
    "",
    response_model=Ejemplar,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(exigir_api_key)],
    summary="Registrar un ejemplar",
)
def crear(datos: EjemplarCrear, conn: sqlite3.Connection = Depends(obtener_db)):
    return crud.crear(conn, "ejemplares", datos.model_dump())


@router.patch(
    "/{ejemplar_id}",
    response_model=Ejemplar,
    dependencies=[Depends(exigir_api_key)],
    summary="Editar un ejemplar (préstamos, ubicación, estado)",
)
def editar(
    ejemplar_id: int, datos: EjemplarEditar, conn: sqlite3.Connection = Depends(obtener_db)
):
    actual = crud.obtener(conn, "ejemplares", ejemplar_id)
    if actual is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe el ejemplar {ejemplar_id}.")

    cambios = datos.model_dump(exclude_unset=True)

    # El CHECK del esquema mira la fila resultante, no solo lo enviado: hay que
    # validar la combinación de lo que ya había con lo que llega.
    resultante = {**actual, **cambios}
    if resultante.get("en_prestamo") and not resultante.get("prestado_a"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Un ejemplar en préstamo necesita 'prestado_a'.",
        )

    return crud.actualizar(conn, "ejemplares", ejemplar_id, cambios)


@router.delete(
    "/{ejemplar_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(exigir_api_key)],
    summary="Borrar un ejemplar",
)
def borrar(ejemplar_id: int, conn: sqlite3.Connection = Depends(obtener_db)) -> None:
    if not crud.borrar(conn, "ejemplares", ejemplar_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe el ejemplar {ejemplar_id}.")
