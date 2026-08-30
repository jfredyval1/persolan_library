"""Cliente de Google Books, usado como respaldo de Open Library.

Suele tener mejor cobertura de ediciones recientes y en español, e incluye
descripción e idioma sin consultas adicionales.
"""

import httpx

from ..config import GOOGLE_API_KEY
from ..schemas import FichaISBN
from .comun import normalizar_idioma, parsear_fecha

BASE = "https://www.googleapis.com/books/v1/volumes"


async def buscar(cliente: httpx.AsyncClient, isbn: str) -> FichaISBN | None:
    # Sin clave Google responde 429 a cualquier consulta: el consumidor anónimo
    # tiene la cuota diaria puesta a 0, así que no es un límite que se agote
    # sino la ausencia de acceso.
    #
    # Va por cabecera y no como ?key=: httpx incluye la URL completa en el texto
    # de sus excepciones, así que un simple 503 dejaría la clave escrita en el
    # log. La cabecera no aparece ahí.
    cabeceras = {"X-goog-api-key": GOOGLE_API_KEY} if GOOGLE_API_KEY else None

    resp = await cliente.get(BASE, params={"q": f"isbn:{isbn}"}, headers=cabeceras)
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
        # Google manda pageCount 0 cuando no sabe las páginas, y 0 no es un
        # número de páginas: el modelo de salida exige >= 1 y reventaría al
        # serializar la respuesta.
        numero_paginas=info.get("pageCount") or None,
        sinopsis=info.get("description"),
        portada_path=portada,
        editorial=info.get("publisher"),
        autores=list(info.get("authors") or []),
    )
