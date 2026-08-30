"""Orquestación del alta por ISBN: consultar fuentes y persistir la ficha."""

import logging
import sqlite3

import httpx

from .. import crud
from ..config import TIMEOUT_HTTP
from ..schemas import DesdeISBN, FichaISBN
from . import googlebooks, openlibrary

log = logging.getLogger("biblioteca")


class FuentesNoDisponibles(RuntimeError):
    """Ninguna de las fuentes externas pudo responder."""


def cliente_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT_HTTP,
        follow_redirects=True,
        headers={"User-Agent": "biblioteca-personal/1.0 (uso personal)"},
    )


async def buscar_ficha(cliente: httpx.AsyncClient, isbn: str) -> FichaISBN | None:
    """Open Library primero, Google Books si no lo encuentra.

    Devuelve None solo cuando ambas fuentes han respondido y ninguna conoce el
    ISBN. Si alguna falla (sin red, o el 429 con el que Google Books limita el
    uso anónimo) lanza FuentesNoDisponibles: "no lo encuentro" y "no he podido
    preguntar" son cosas distintas, y confundirlas daría por inexistente un
    libro que sí está catalogado.
    """
    fallidas: list[str] = []

    for nombre, fuente in (("Open Library", openlibrary), ("Google Books", googlebooks)):
        try:
            ficha = await fuente.buscar(cliente, isbn)
            if ficha is not None:
                return ficha
        except (httpx.HTTPError, ValueError) as exc:
            fallidas.append(f"{nombre} ({exc.__class__.__name__})")
            log.warning("%s no respondió para el ISBN %s: %s", nombre, isbn, exc)

    if fallidas:
        raise FuentesNoDisponibles(
            f"No se puede confirmar si el ISBN {isbn} existe: no respondió "
            + " ni ".join(fallidas)
            + ". Comprueba la conexión y reinténtalo en unos minutos."
        )
    return None


def persistir_ficha(
    conn: sqlite3.Connection, ficha: FichaISBN, extras: DesdeISBN | None = None
) -> dict:
    """Crea libro, autores, editorial y (opcionalmente) un ejemplar inicial.

    El llamador controla la transacción: aquí no se hace commit.
    """
    editorial_id = (
        crud.buscar_o_crear_editorial(conn, ficha.editorial) if ficha.editorial else None
    )

    libro = crud.crear(
        conn,
        "libros",
        {
            "titulo": ficha.titulo,
            "titulo_original": ficha.titulo_original,
            "isbn": ficha.isbn,
            "idioma": ficha.idioma,
            "dewey_codigo_completo": ficha.dewey_codigo_completo,
            "dewey_categoria_id": crud.categoria_dewey_existente(
                conn, ficha.dewey_codigo_completo
            ),
            "fecha_publicacion": ficha.fecha_publicacion,
            "numero_paginas": ficha.numero_paginas,
            "sinopsis": ficha.sinopsis,
            "portada_path": ficha.portada_path,
            "editorial_id": editorial_id,
        },
    )

    autor_ids = [crud.buscar_o_crear_autor(conn, nombre) for nombre in ficha.autores]
    if autor_ids:
        crud.reemplazar_relacion(conn, "libro_autor", "autor_id", libro["id"], autor_ids)

    if extras and _pide_ejemplar(extras):
        crud.crear(
            conn,
            "ejemplares",
            {
                "libro_id": libro["id"],
                "estado_fisico": extras.estado_fisico,
                "formato": extras.formato,
                "fecha_adquisicion": extras.fecha_adquisicion,
                "precio_compra": extras.precio_compra,
                "modulo_id": extras.modulo_id,
                "tiene_hongos": extras.tiene_hongos,
                "requiere_reparacion": extras.requiere_reparacion,
                "en_prestamo": 0,
                "notas": extras.notas,
            },
        )

    return crud.detalle_libro(conn, libro["id"])


def _pide_ejemplar(extras: DesdeISBN) -> bool:
    # tiene_hongos y requiere_reparacion no cuentan: valen False por defecto y
    # decir «no tiene hongos» de un libro que no se tiene no pide un ejemplar.
    return any(
        v is not None
        for v in (
            extras.modulo_id,
            extras.estado_fisico,
            extras.formato,
            extras.fecha_adquisicion,
            extras.precio_compra,
            extras.notas,
        )
    )
