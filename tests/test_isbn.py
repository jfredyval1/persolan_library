"""Alta por ISBN e importación en lote, con las fuentes externas simuladas.

Se sustituye solo el transporte HTTP: el código de los clientes (parseo de
fechas, idiomas, Dewey y autores) se ejecuta de verdad.
"""

import httpx
import pytest

from api.services import mapper

from .conftest import CLAVE

MR_FOX = "9780140328721"        # solo en Open Library
SILENCIO = "9788420471839"      # solo en Google Books
DESCONOCIDO = "9780306406157"   # en ninguna de las dos
INVALIDO = "9780140328722"      # dígito de control incorrecto

OPEN_LIBRARY = {
    MR_FOX: {
        "title": "Fantastic Mr. Fox",
        "subtitle": "A play",
        "authors": [{"name": "Roald Dahl"}],
        "number_of_pages": 96,
        "publishers": [{"name": "Puffin"}],
        "publish_date": "October 1, 1988",
        "cover": {"medium": "https://covers.example/m.jpg", "large": "https://covers.example/l.jpg"},
        "classifications": {"dewey_decimal_class": ["823.914"]},
    }
}

EDICIONES = {
    MR_FOX: {
        "languages": [{"key": "/languages/eng"}],
        "description": {"value": "Tres granjeros intentan cazar a un zorro astuto."},
    }
}

GOOGLE_BOOKS = {
    SILENCIO: {
        "title": "El silencio de la ciudad blanca",
        "authors": ["Eva García Sáenz de Urturi"],
        "publisher": "Planeta",
        "publishedDate": "2016",
        "pageCount": 496,
        "language": "es",
        "description": "Un thriller ambientado en Vitoria.",
        "imageLinks": {"thumbnail": "https://books.example/t.jpg"},
    }
}


def _manejador(peticion: httpx.Request) -> httpx.Response:
    url = str(peticion.url)

    if "openlibrary.org/api/books" in url:
        isbn = peticion.url.params["bibkeys"].split(":", 1)[1]
        datos = OPEN_LIBRARY.get(isbn)
        return httpx.Response(200, json={f"ISBN:{isbn}": datos} if datos else {})

    if "openlibrary.org/isbn/" in url:
        isbn = url.rsplit("/", 1)[-1].removesuffix(".json")
        edicion = EDICIONES.get(isbn)
        return httpx.Response(200, json=edicion) if edicion else httpx.Response(404)

    if "googleapis.com/books" in url:
        isbn = peticion.url.params["q"].split(":", 1)[1]
        info = GOOGLE_BOOKS.get(isbn)
        return httpx.Response(200, json={"items": [{"volumeInfo": info}]} if info else {})

    raise AssertionError(f"Petición inesperada a {url}")


@pytest.fixture(autouse=True)
def fuentes_simuladas(monkeypatch):
    monkeypatch.setattr(
        mapper,
        "cliente_http",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(_manejador)),
    )


# ------------------------------------------------------------------- lookup
def test_lookup_normaliza_la_ficha_de_open_library(cliente):
    ficha = cliente.get(f"/lookup/{MR_FOX}").json()

    assert ficha["fuente"] == "openlibrary"
    assert ficha["titulo"] == "Fantastic Mr. Fox"
    assert ficha["autores"] == ["Roald Dahl"]
    assert ficha["editorial"] == "Puffin"
    assert ficha["fecha_publicacion"] == "1988-10-01"   # "October 1, 1988"
    assert ficha["idioma"] == "en"                       # "eng" -> "en"
    assert ficha["dewey_codigo_completo"] == "823.914"
    assert ficha["sinopsis"].startswith("Tres granjeros")

    # No debe haber escrito nada.
    assert cliente.get("/libros").json() == []


def test_lookup_cae_en_google_books(cliente):
    ficha = cliente.get(f"/lookup/{SILENCIO}").json()
    assert ficha["fuente"] == "googlebooks"
    assert ficha["fecha_publicacion"] == "2016-01-01"    # solo se conocía el año
    assert ficha["numero_paginas"] == 496


def test_lookup_acepta_isbn_con_guiones(cliente):
    assert cliente.get("/lookup/978-0-14-032872-1").json()["isbn"] == MR_FOX


def test_lookup_rechaza_isbn_mal_tecleado(cliente):
    resp = cliente.get(f"/lookup/{INVALIDO}")
    assert resp.status_code == 422
    assert "dígito de control" in resp.json()["detail"]


def test_lookup_de_isbn_desconocido(cliente):
    assert cliente.get(f"/lookup/{DESCONOCIDO}").status_code == 404


# -------------------------------------------------------------- desde-isbn
def test_alta_desde_isbn_crea_autor_y_editorial(cliente):
    resp = cliente.post("/libros/desde-isbn", json={"isbn": MR_FOX}, headers=CLAVE)
    assert resp.status_code == 201, resp.text
    libro = resp.json()

    assert libro["fuente"] == "openlibrary"
    assert libro["titulo"] == "Fantastic Mr. Fox"
    assert libro["editorial"]["nombre"] == "Puffin"
    assert (libro["autores"][0]["nombre"], libro["autores"][0]["apellidos"]) == ("Roald", "Dahl")
    # 823.914 -> categoría 823 no existe en la semilla (solo clases y divisiones)
    assert libro["dewey_codigo_completo"] == "823.914"
    assert libro["dewey_categoria_id"] is None

    assert cliente.get("/autores", params={"q": "Roald"}).json()
    assert cliente.get("/editoriales", params={"q": "Puffin"}).json()


def test_alta_desde_isbn_reutiliza_autor_y_editorial_existentes(cliente):
    cliente.post("/libros/desde-isbn", json={"isbn": MR_FOX}, headers=CLAVE)
    cliente.delete("/libros/1", headers=CLAVE)
    cliente.post("/libros/desde-isbn", json={"isbn": MR_FOX}, headers=CLAVE)

    assert len(cliente.get("/autores").json()) == 1
    assert len(cliente.get("/editoriales").json()) == 1


def test_alta_desde_isbn_puede_crear_el_ejemplar(cliente):
    ubicacion = cliente.post("/ubicaciones", json={"nombre": "repisa_1"}, headers=CLAVE).json()

    libro = cliente.post(
        "/libros/desde-isbn",
        json={"isbn": MR_FOX, "ubicacion_id": ubicacion["id"], "estado_fisico": "bueno"},
        headers=CLAVE,
    ).json()

    assert len(libro["ejemplares"]) == 1
    assert libro["ejemplares"][0]["ubicacion_id"] == ubicacion["id"]
    assert libro["ejemplares"][0]["en_prestamo"] is False


def test_alta_desde_isbn_sin_ejemplar_por_defecto(cliente):
    libro = cliente.post("/libros/desde-isbn", json={"isbn": MR_FOX}, headers=CLAVE).json()
    assert libro["ejemplares"] == []


def test_alta_desde_isbn_duplicada_da_409(cliente):
    cliente.post("/libros/desde-isbn", json={"isbn": MR_FOX}, headers=CLAVE)
    resp = cliente.post("/libros/desde-isbn", json={"isbn": MR_FOX}, headers=CLAVE)

    assert resp.status_code == 409
    assert "Fantastic Mr. Fox" in resp.json()["detail"]


def test_alta_desde_isbn_exige_clave(cliente):
    assert cliente.post("/libros/desde-isbn", json={"isbn": MR_FOX}).status_code == 401


def test_una_fuente_caida_no_se_confunde_con_no_encontrado(cliente, monkeypatch):
    """Google Books limita el uso anónimo con 429; eso no es 'el libro no existe'."""

    def manejador_con_429(peticion: httpx.Request) -> httpx.Response:
        if "googleapis.com" in str(peticion.url):
            return httpx.Response(429, json={"error": "rate limited"})
        return _manejador(peticion)

    monkeypatch.setattr(
        mapper,
        "cliente_http",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(manejador_con_429)),
    )

    resp = cliente.get(f"/lookup/{DESCONOCIDO}")
    assert resp.status_code == 503
    assert "Google Books" in resp.json()["detail"]

    # Y en un lote se marca como error (reintentable), no como no_encontrado.
    informe = cliente.post(
        "/importar/isbns", json={"isbns": [DESCONOCIDO]}, headers=CLAVE
    ).json()
    assert (informe["errores"], informe["no_encontrados"]) == (1, 0)


# -------------------------------------------------------------- importación
def test_importar_lista_de_isbns(cliente):
    cliente.post("/libros/desde-isbn", json={"isbn": SILENCIO}, headers=CLAVE)

    informe = cliente.post(
        "/importar/isbns",
        json={"isbns": [MR_FOX, SILENCIO, DESCONOCIDO, INVALIDO]},
        headers=CLAVE,
    ).json()

    assert (informe["creados"], informe["duplicados"]) == (1, 1)
    assert (informe["no_encontrados"], informe["errores"]) == (1, 1)

    por_estado = {f["estado"]: f for f in informe["filas"]}
    assert por_estado["creado"]["titulo"] == "Fantastic Mr. Fox"
    assert "dígito de control" in por_estado["error"]["detalle"]

    # Lo creado antes del fallo sigue ahí: cada fila va en su transacción.
    assert len(cliente.get("/libros").json()) == 2


def test_importar_csv_mezcla_isbn_y_alta_manual(cliente):
    ubicacion = cliente.post("/ubicaciones", json={"nombre": "central"}, headers=CLAVE).json()
    csv = (
        "isbn,titulo,autor,editorial,anio,paginas,idioma,ubicacion_id,estado_fisico\n"
        f"{MR_FOX},,,,,,,{ubicacion['id']},bueno\n"
        ",Rayuela,Julio Cortázar,Sudamericana,1963,736,es,"
        f"{ubicacion['id']},regular\n"
        ",,,,,,,,\n"
    )

    informe = cliente.post(
        "/importar/csv",
        files={"archivo": ("libros.csv", csv, "text/csv")},
        headers=CLAVE,
    ).json()

    assert (informe["total"], informe["creados"], informe["errores"]) == (3, 2, 1)

    rayuela = cliente.get("/libros", params={"q": "Rayuela"}).json()[0]
    assert rayuela["numero_paginas"] == 736
    assert rayuela["fecha_publicacion"] == "1963-01-01"
    assert rayuela["editorial"]["nombre"] == "Sudamericana"
    assert rayuela["autores"][0]["apellidos"] == "Cortázar"
    assert rayuela["ejemplares"][0]["estado_fisico"] == "regular"


def test_importar_csv_marca_el_estado_fisico_invalido_como_error_de_fila(cliente):
    csv = f"isbn,estado_fisico\n{MR_FOX},flamante\n{SILENCIO},nuevo\n"

    informe = cliente.post(
        "/importar/csv", files={"archivo": ("x.csv", csv, "text/csv")}, headers=CLAVE
    ).json()

    assert (informe["creados"], informe["errores"]) == (1, 1)
    assert len(cliente.get("/libros").json()) == 1


def test_importar_csv_sin_cabecera_da_422(cliente):
    resp = cliente.post(
        "/importar/csv", files={"archivo": ("x.csv", "", "text/csv")}, headers=CLAVE
    )
    assert resp.status_code == 422
