"""Cliente de Open Library.

Fuente principal: cubre bien el fondo en inglés y buena parte del español,
no exige clave y devuelve la clasificación Dewey, que Google Books no da.
"""

import httpx

from ..schemas import FichaISBN
from .comun import normalizar_idioma, parsear_fecha

BASE = "https://openlibrary.org"


async def buscar(cliente: httpx.AsyncClient, isbn: str) -> FichaISBN | None:
    resp = await cliente.get(
        f"{BASE}/api/books",
        params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
    )
    resp.raise_for_status()
    datos = resp.json().get(f"ISBN:{isbn}")
    if not datos:
        return None

    clasif = datos.get("classifications") or {}
    dewey = (clasif.get("dewey_decimal_class") or [None])[0]
    portada = (datos.get("cover") or {}).get("large") or (datos.get("cover") or {}).get("medium")

    ficha = FichaISBN(
        fuente="openlibrary",
        isbn=isbn,
        titulo=datos.get("title") or "(sin título)",
        titulo_original=datos.get("subtitle"),
        fecha_publicacion=parsear_fecha(datos.get("publish_date")),
        numero_paginas=datos.get("number_of_pages") or None,  # 0 no es un número de páginas
        portada_path=portada,
        dewey_codigo_completo=dewey,
        editorial=(datos.get("publishers") or [{}])[0].get("name"),
        autores=[a["name"] for a in datos.get("authors") or [] if a.get("name")],
    )

    # jscmd=data no trae idioma ni descripción; la ficha de edición sí.
    # Es una consulta extra y opcional: si falla, se devuelve lo que ya hay.
    await _completar_desde_edicion(cliente, isbn, ficha)
    return ficha


async def _completar_desde_edicion(
    cliente: httpx.AsyncClient, isbn: str, ficha: FichaISBN
) -> None:
    try:
        resp = await cliente.get(f"{BASE}/isbn/{isbn}.json")
        if resp.status_code != 200:
            return
        edicion = resp.json()
    except (httpx.HTTPError, ValueError):
        return

    idiomas = edicion.get("languages") or []
    if idiomas:
        # {"key": "/languages/spa"} -> "spa"
        ficha.idioma = normalizar_idioma(idiomas[0].get("key", "").rsplit("/", 1)[-1])

    descripcion = edicion.get("description")
    if isinstance(descripcion, dict):
        descripcion = descripcion.get("value")
    if descripcion:
        ficha.sinopsis = descripcion
