"""Importación en lote, por lista de ISBNs o por CSV.

Cada fila se confirma por separado: un fallo en la fila 40 no debe deshacer
las 39 que ya habían entrado bien.
"""

import asyncio
import csv
import io
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError

from .. import crud
from ..config import PAUSA_ENTRE_CONSULTAS
from ..db import obtener_db
from ..schemas import DesdeISBN, InformeImportacion, LoteISBN, ResultadoFila
from ..security import exigir_api_key
from ..services import mapper
from ..services.comun import ISBNInvalido, normalizar_isbn

router = APIRouter(
    prefix="/importar", tags=["importación"], dependencies=[Depends(exigir_api_key)]
)

COLUMNAS_CSV = (
    "isbn, titulo, autor, editorial, anio, paginas, idioma, "
    "modulo_id, estado_fisico, notas"
)


def _informe(filas: list[ResultadoFila]) -> InformeImportacion:
    cuenta = lambda estado: sum(1 for f in filas if f.estado == estado)  # noqa: E731
    return InformeImportacion(
        total=len(filas),
        creados=cuenta("creado"),
        duplicados=cuenta("duplicado"),
        no_encontrados=cuenta("no_encontrado"),
        errores=cuenta("error"),
        filas=filas,
    )


async def _procesar_isbn(
    conn: sqlite3.Connection,
    cliente,
    numero: int,
    bruto: str,
    extras: DesdeISBN,
) -> ResultadoFila:
    """Procesa un ISBN y confirma o deshace solo esa fila."""
    try:
        isbn = normalizar_isbn(bruto)
    except ISBNInvalido as exc:
        return ResultadoFila(fila=numero, isbn=bruto, estado="error", detalle=str(exc))

    existente = crud.libro_por_isbn(conn, isbn)
    if existente:
        return ResultadoFila(
            fila=numero, isbn=isbn, titulo=existente["titulo"], estado="duplicado",
            libro_id=existente["id"], detalle="Ya estaba en la biblioteca.",
        )

    try:
        ficha = await mapper.buscar_ficha(cliente, isbn)
    except mapper.FuentesNoDisponibles as exc:
        return ResultadoFila(fila=numero, isbn=isbn, estado="error", detalle=str(exc))

    if ficha is None:
        return ResultadoFila(
            fila=numero, isbn=isbn, estado="no_encontrado",
            detalle="Ninguna fuente conoce este ISBN.",
        )

    try:
        libro = mapper.persistir_ficha(conn, ficha, extras)
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        return ResultadoFila(fila=numero, isbn=isbn, estado="error", detalle=str(exc))

    return ResultadoFila(
        fila=numero, isbn=isbn, titulo=libro["titulo"], estado="creado",
        libro_id=libro["id"], detalle=f"Datos de {ficha.fuente}.",
    )


@router.post(
    "/isbns",
    response_model=InformeImportacion,
    summary="Dar de alta una lista de ISBNs",
)
async def importar_isbns(lote: LoteISBN, conn: sqlite3.Connection = Depends(obtener_db)):
    extras = DesdeISBN(
        isbn="", modulo_id=lote.modulo_id, estado_fisico=lote.estado_fisico
    )
    filas: list[ResultadoFila] = []

    async with mapper.cliente_http() as cliente:
        for numero, bruto in enumerate(lote.isbns, start=1):
            if numero > 1:
                # Cortesía con dos APIs públicas y gratuitas.
                await asyncio.sleep(PAUSA_ENTRE_CONSULTAS)
            filas.append(await _procesar_isbn(conn, cliente, numero, bruto, extras))

    return _informe(filas)


def _resumir(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
    )


def _entero(valor: str | None) -> int | None:
    valor = (valor or "").strip()
    return int(valor) if valor.isdigit() else None


def _crear_desde_columnas(conn: sqlite3.Connection, numero: int, fila: dict) -> ResultadoFila:
    """Alta manual para las filas del CSV que no traen ISBN."""
    titulo = (fila.get("titulo") or "").strip()
    if not titulo:
        return ResultadoFila(
            fila=numero, estado="error", detalle="La fila no tiene ni 'isbn' ni 'titulo'."
        )

    try:
        editorial = (fila.get("editorial") or "").strip()
        anio = _entero(fila.get("anio"))
        libro = crud.crear(conn, "libros", {
            "titulo": titulo,
            "idioma": (fila.get("idioma") or "").strip() or None,
            "fecha_publicacion": f"{anio}-01-01" if anio else None,
            "numero_paginas": _entero(fila.get("paginas")),
            "editorial_id": crud.buscar_o_crear_editorial(conn, editorial) if editorial else None,
        })

        autor = (fila.get("autor") or "").strip()
        if autor:
            crud.reemplazar_relacion(
                conn, "libro_autor", "autor_id", libro["id"],
                [crud.buscar_o_crear_autor(conn, a.strip()) for a in autor.split(";") if a.strip()],
            )

        modulo_id = _entero(fila.get("modulo_id"))
        estado_fisico = (fila.get("estado_fisico") or "").strip() or None
        if modulo_id or estado_fisico:
            crud.crear(conn, "ejemplares", {
                "libro_id": libro["id"],
                "modulo_id": modulo_id,
                "estado_fisico": estado_fisico,
                "notas": (fila.get("notas") or "").strip() or None,
                "en_prestamo": 0,
            })

        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        return ResultadoFila(fila=numero, titulo=titulo, estado="error", detalle=str(exc))

    return ResultadoFila(
        fila=numero, titulo=titulo, estado="creado", libro_id=libro["id"],
        detalle="Alta manual (la fila no traía ISBN).",
    )


@router.post(
    "/csv",
    response_model=InformeImportacion,
    summary=f"Importar un CSV con las columnas: {COLUMNAS_CSV}",
)
async def importar_csv(
    archivo: UploadFile = File(..., description=f"CSV con cabecera. Columnas: {COLUMNAS_CSV}"),
    conn: sqlite3.Connection = Depends(obtener_db),
):
    contenido = (await archivo.read()).decode("utf-8-sig", errors="replace")
    lector = csv.DictReader(io.StringIO(contenido))
    if not lector.fieldnames:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"El CSV está vacío o no tiene cabecera. Columnas reconocidas: {COLUMNAS_CSV}.",
        )

    # Nombres de columna tolerantes a mayúsculas y espacios.
    normalizar = lambda d: {(k or "").strip().lower(): v for k, v in d.items()}  # noqa: E731
    filas_csv = [normalizar(f) for f in lector]

    resultados: list[ResultadoFila] = []
    async with mapper.cliente_http() as cliente:
        consultadas = 0
        for numero, fila in enumerate(filas_csv, start=1):
            bruto = (fila.get("isbn") or "").strip()
            if bruto:
                if consultadas:
                    await asyncio.sleep(PAUSA_ENTRE_CONSULTAS)
                consultadas += 1
                try:
                    extras = DesdeISBN(
                        isbn=bruto,
                        modulo_id=_entero(fila.get("modulo_id")),
                        estado_fisico=(fila.get("estado_fisico") or "").strip() or None,
                        notas=(fila.get("notas") or "").strip() or None,
                    )
                except ValidationError as exc:
                    # p. ej. un estado_fisico fuera de la lista permitida: es un
                    # fallo de esa fila, no de la importación entera.
                    resultados.append(ResultadoFila(
                        fila=numero, isbn=bruto, estado="error", detalle=_resumir(exc)
                    ))
                    continue
                resultados.append(await _procesar_isbn(conn, cliente, numero, bruto, extras))
            else:
                resultados.append(_crear_desde_columnas(conn, numero, fila))

    return _informe(resultados)
