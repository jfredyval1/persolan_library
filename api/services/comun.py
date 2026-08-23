"""Utilidades compartidas por los clientes de fuentes externas."""

import re
from datetime import date, datetime

# Open Library devuelve ISO 639-2 ("spa"), Google Books ISO 639-1 ("es").
# Se normaliza a dos letras, que es lo que se guarda en libros.idioma.
_IDIOMAS = {
    "spa": "es", "eng": "en", "fre": "fr", "fra": "fr", "ger": "de", "deu": "de",
    "ita": "it", "por": "pt", "cat": "ca", "glg": "gl", "eus": "eu", "baq": "eu",
    "lat": "la", "rus": "ru", "jpn": "ja", "chi": "zh", "zho": "zh", "ara": "ar",
    "nld": "nl", "dut": "nl", "swe": "sv", "nor": "no", "dan": "da", "pol": "pl",
    "grc": "grc", "gre": "el", "ell": "el", "tur": "tr", "heb": "he", "kor": "ko",
}

_FORMATOS_FECHA = (
    "%Y-%m-%d", "%Y-%m", "%Y",
    "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
    "%B %Y", "%b %Y", "%d/%m/%Y",
)


class ISBNInvalido(ValueError):
    pass


def normalizar_isbn(bruto: str) -> str:
    """Quita guiones y espacios, valida longitud y dígito de control.

    La comprobación del dígito de control no es un lujo: al cargar decenas de
    libros seguidos, un ISBN mal tecleado se detecta aquí en vez de acabar en
    una consulta inútil o, peor, en un registro erróneo.
    """
    isbn = re.sub(r"[\s-]", "", bruto or "").upper()

    if len(isbn) == 10:
        if not re.fullmatch(r"\d{9}[\dX]", isbn):
            raise ISBNInvalido(f"'{bruto}' no tiene forma de ISBN-10.")
        suma = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(isbn))
        if suma % 11 != 0:
            raise ISBNInvalido(f"'{bruto}': dígito de control incorrecto (ISBN-10).")
        return isbn

    if len(isbn) == 13:
        if not isbn.isdigit():
            raise ISBNInvalido(f"'{bruto}' no tiene forma de ISBN-13.")
        suma = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(isbn))
        if suma % 10 != 0:
            raise ISBNInvalido(f"'{bruto}': dígito de control incorrecto (ISBN-13).")
        return isbn

    raise ISBNInvalido(f"'{bruto}' no mide 10 ni 13 caracteres.")


def parsear_fecha(bruto: str | None) -> date | None:
    """Acepta los muchos formatos que devuelven las fuentes externas.

    Cuando solo se conoce el año (o el mes), se completa con el día 1: la
    columna es DATE y no admite fechas parciales.
    """
    if not bruto:
        return None
    texto = str(bruto).strip()
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    # Último recurso: cualquier año de cuatro cifras dentro del texto.
    anio = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", texto)
    return date(int(anio.group(1)), 1, 1) if anio else None


def normalizar_idioma(bruto: str | None) -> str | None:
    if not bruto:
        return None
    codigo = bruto.strip().lower()
    return _IDIOMAS.get(codigo, codigo)
