"""CRUD de libros, incluyendo las relaciones N:M con autores y géneros."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import crud
from ..db import obtener_db
from ..schemas import LibroCrear, LibroDetalle, LibroEditar
from ..security import exigir_api_key

router = APIRouter(prefix="/libros", tags=["libros"])


@router.get("", response_model=list[LibroDetalle], summary="Listar libros")
def listar(
    q: str | None = Query(None, description="Filtro por título"),
    editorial_id: int | None = None,
    idioma: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(obtener_db),
):
    libros = crud.listar(
        conn, "libros",
        limit=limit, offset=offset, q=q,
        filtros={"editorial_id": editorial_id, "idioma": idioma},
    )
    return [crud.detalle_libro(conn, libro["id"]) for libro in libros]


@router.get("/{libro_id}", response_model=LibroDetalle, summary="Ficha completa de un libro")
def obtener(libro_id: int, conn: sqlite3.Connection = Depends(obtener_db)):
    libro = crud.detalle_libro(conn, libro_id)
    if libro is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe el libro {libro_id}.")
    return libro


@router.post(
    "",
    response_model=LibroDetalle,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(exigir_api_key)],
    summary="Crear un libro con sus autores y géneros",
)
def crear(datos: LibroCrear, conn: sqlite3.Connection = Depends(obtener_db)):
    campos = datos.model_dump()
    autor_ids = campos.pop("autor_ids")
    genero_ids = campos.pop("genero_ids")

    libro = crud.crear(conn, "libros", campos)
    crud.reemplazar_relacion(conn, "libro_autor", "autor_id", libro["id"], autor_ids)
    crud.reemplazar_relacion(conn, "libro_genero", "genero_id", libro["id"], genero_ids)
    return crud.detalle_libro(conn, libro["id"])


@router.patch(
    "/{libro_id}",
    response_model=LibroDetalle,
    dependencies=[Depends(exigir_api_key)],
    summary="Editar un libro",
)
def editar(libro_id: int, datos: LibroEditar, conn: sqlite3.Connection = Depends(obtener_db)):
    cambios = datos.model_dump(exclude_unset=True)
    # Omitir la lista deja la relación intacta; enviarla la reemplaza entera.
    autor_ids = cambios.pop("autor_ids", None)
    genero_ids = cambios.pop("genero_ids", None)

    if cambios:
        if crud.actualizar(conn, "libros", libro_id, cambios) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe el libro {libro_id}.")
    elif crud.obtener(conn, "libros", libro_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe el libro {libro_id}.")

    if autor_ids is not None:
        crud.reemplazar_relacion(conn, "libro_autor", "autor_id", libro_id, autor_ids)
    if genero_ids is not None:
        crud.reemplazar_relacion(conn, "libro_genero", "genero_id", libro_id, genero_ids)

    return crud.detalle_libro(conn, libro_id)


@router.delete(
    "/{libro_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(exigir_api_key)],
    summary="Borrar un libro (arrastra sus ejemplares y relaciones)",
)
def borrar(libro_id: int, conn: sqlite3.Connection = Depends(obtener_db)) -> None:
    if not crud.borrar(conn, "libros", libro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe el libro {libro_id}.")
