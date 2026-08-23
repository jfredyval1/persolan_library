"""Alta de libros a partir del ISBN.

Es el atajo que evita teclear a mano título, autor, editorial y páginas.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .. import crud
from ..db import obtener_db
from ..schemas import DesdeISBN, FichaISBN, LibroCreadoDesdeISBN
from ..security import exigir_api_key
from ..services import mapper
from ..services.comun import ISBNInvalido, normalizar_isbn

router = APIRouter(tags=["ISBN"])


def _normalizar(bruto: str) -> str:
    try:
        return normalizar_isbn(bruto)
    except ISBNInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


async def _buscar(isbn: str) -> FichaISBN:
    async with mapper.cliente_http() as cliente:
        try:
            ficha = await mapper.buscar_ficha(cliente, isbn)
        except mapper.FuentesNoDisponibles as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    if ficha is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Ninguna fuente conoce el ISBN {isbn}. Créalo a mano con POST /libros.",
        )
    return ficha


@router.get(
    "/lookup/{isbn}",
    response_model=FichaISBN,
    tags=["ISBN"],
    summary="Consultar un ISBN sin guardar nada",
)
async def lookup(isbn: str):
    return await _buscar(_normalizar(isbn))


@router.post(
    "/libros/desde-isbn",
    response_model=LibroCreadoDesdeISBN,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(exigir_api_key)],
    summary="Buscar un ISBN y darlo de alta (crea autor y editorial si hacen falta)",
)
async def desde_isbn(datos: DesdeISBN, conn: sqlite3.Connection = Depends(obtener_db)):
    isbn = _normalizar(datos.isbn)

    existente = crud.libro_por_isbn(conn, isbn)
    if existente:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ya existe un libro con ese ISBN: «{existente['titulo']}» (id {existente['id']}).",
        )

    ficha = await _buscar(isbn)
    libro = mapper.persistir_ficha(conn, ficha, datos)
    return {**libro, "fuente": ficha.fuente}
