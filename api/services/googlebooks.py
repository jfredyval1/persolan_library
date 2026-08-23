"""Cliente de Google Books, usado como respaldo de Open Library.

Suele tener mejor cobertura de ediciones recientes y en español, e incluye
descripción e idioma sin consultas adicionales.
"""

import httpx

from ..schemas import FichaISBN
from .comun import normalizar_idioma, parsear_fecha

BASE = "https://www.googleapis.com/books/v1/volumes"


async def buscar(cliente: httpx.AsyncClient, isbn: str) -> FichaISBN | None:
    resp = await cliente.get(BASE, params={"q": f"isbn:{isbn}"})
    resp.raise_for_status()
    elementos = resp.json().get("items") or []
    if not elementos:
        return None

    info = elementos[0].get("volumeInfo") or {}
    portada = (info.get("imageLinks") or {}).get("thumbnail")

    return FichaISBN(
        fuente="googlebooks",
        isbn=isbn,
        titulo=info.get("title") or "(sin título)",
        titulo_original=info.get("subtitle"),
        idioma=normalizar_idioma(info.get("language")),
        fecha_publicacion=parsear_fecha(info.get("publishedDate")),
        numero_paginas=info.get("pageCount"),
        sinopsis=info.get("description"),
        portada_path=portada,
        editorial=info.get("publisher"),
        autores=list(info.get("authors") or []),
    )
