"""CRUD, restricciones del esquema e integridad del contenedor GeoPackage."""

import sqlite3

from .conftest import CLAVE, GPKG


def test_salud_responde_con_el_gpkg(cliente):
    datos = cliente.get("/salud").json()
    assert datos["libros"] == 0
    assert "libros" in datos["ultimo_cambio_por_tabla"]


def test_las_semillas_estan_cargadas(cliente):
    assert cliente.get("/paises/ES").json()["nombre"] == "España"
    assert cliente.get("/dewey/860").json()["descripcion"] == "Literaturas española y portuguesa"
    assert cliente.get("/dewey/860").json()["padre_codigo"] == "800"


def test_alta_de_libro_con_autores_y_generos(cliente):
    autor = cliente.post(
        "/autores", json={"nombre": "Gabriel", "apellidos": "García Márquez", "pais_id": "CO"},
        headers=CLAVE,
    ).json()
    editorial = cliente.post(
        "/editoriales", json={"nombre": "Sudamericana", "pais_id": "AR"}, headers=CLAVE
    ).json()
    genero = cliente.post("/generos", json={"nombre": "Realismo mágico"}, headers=CLAVE).json()

    resp = cliente.post(
        "/libros",
        json={
            "titulo": "Cien años de soledad",
            "isbn": "9780307474728",
            "idioma": "es",
            "fecha_publicacion": "1967-05-30",
            "numero_paginas": 471,
            "editorial_id": editorial["id"],
            "autor_ids": [autor["id"]],
            "genero_ids": [genero["id"]],
        },
        headers=CLAVE,
    )
    assert resp.status_code == 201, resp.text
    libro = resp.json()
    assert [a["apellidos"] for a in libro["autores"]] == ["García Márquez"]
    assert libro["editorial"]["nombre"] == "Sudamericana"
    assert libro["generos"][0]["nombre"] == "Realismo mágico"


def test_isbn_duplicado_da_409(cliente):
    cuerpo = {"titulo": "Uno", "isbn": "9780307474728"}
    assert cliente.post("/libros", json=cuerpo, headers=CLAVE).status_code == 201

    resp = cliente.post("/libros", json={**cuerpo, "titulo": "Otro"}, headers=CLAVE)
    assert resp.status_code == 409
    assert "ISBN" in resp.json()["detail"]


def test_patch_reemplaza_la_lista_de_autores(cliente):
    a1 = cliente.post("/autores", json={"nombre": "Ana"}, headers=CLAVE).json()
    a2 = cliente.post("/autores", json={"nombre": "Beto"}, headers=CLAVE).json()
    libro = cliente.post(
        "/libros", json={"titulo": "Dos manos", "autor_ids": [a1["id"]]}, headers=CLAVE
    ).json()

    # Omitir autor_ids deja la relación intacta...
    tras_titulo = cliente.patch(
        f"/libros/{libro['id']}", json={"titulo": "Dos manos (2ª ed.)"}, headers=CLAVE
    ).json()
    assert [a["nombre"] for a in tras_titulo["autores"]] == ["Ana"]

    # ...y enviarla la reemplaza entera.
    tras_autores = cliente.patch(
        f"/libros/{libro['id']}", json={"autor_ids": [a2["id"]]}, headers=CLAVE
    ).json()
    assert [a["nombre"] for a in tras_autores["autores"]] == ["Beto"]


def test_las_claves_foraneas_estan_activas(cliente):
    """Sin PRAGMA foreign_keys=ON esto devolvería 201 en vez de 400."""
    libro = cliente.post("/libros", json={"titulo": "Suelto"}, headers=CLAVE).json()
    resp = cliente.post(
        "/ejemplares", json={"libro_id": libro["id"], "ubicacion_id": 9999}, headers=CLAVE
    )
    assert resp.status_code == 400
    assert "Referencia inexistente" in resp.json()["detail"]


def test_ejemplar_en_prestamo_exige_destinatario(cliente):
    libro = cliente.post("/libros", json={"titulo": "Prestable"}, headers=CLAVE).json()

    resp = cliente.post(
        "/ejemplares", json={"libro_id": libro["id"], "en_prestamo": True}, headers=CLAVE
    )
    assert resp.status_code == 422

    ejemplar = cliente.post(
        "/ejemplares",
        json={"libro_id": libro["id"], "en_prestamo": True, "prestado_a": "Marta"},
        headers=CLAVE,
    ).json()
    assert ejemplar["prestado_a"] == "Marta"

    # Quitar solo el destinatario dejaría la fila incoherente: también se rechaza.
    resp = cliente.patch(
        f"/ejemplares/{ejemplar['id']}", json={"prestado_a": None}, headers=CLAVE
    )
    assert resp.status_code == 422


def test_borrar_libro_arrastra_sus_ejemplares(cliente):
    libro = cliente.post("/libros", json={"titulo": "Efímero"}, headers=CLAVE).json()
    ubicacion = cliente.post("/ubicaciones", json={"nombre": "balda 1"}, headers=CLAVE).json()
    ejemplar = cliente.post(
        "/ejemplares",
        json={"libro_id": libro["id"], "ubicacion_id": ubicacion["id"]},
        headers=CLAVE,
    ).json()

    assert cliente.delete(f"/libros/{libro['id']}", headers=CLAVE).status_code == 204
    assert cliente.get(f"/ejemplares/{ejemplar['id']}").status_code == 404


def test_las_lecturas_son_abiertas_y_las_escrituras_no(cliente):
    assert cliente.get("/libros").status_code == 200

    assert cliente.post("/libros", json={"titulo": "X"}).status_code == 401
    assert cliente.post(
        "/libros", json={"titulo": "X"}, headers={"X-API-Key": "incorrecta"}
    ).status_code == 401


def test_el_filtro_de_texto_mira_varias_columnas(cliente):
    """A un autor se le busca por el apellido tanto como por el nombre."""
    cliente.post(
        "/autores", json={"nombre": "Julio", "apellidos": "Cortázar"}, headers=CLAVE
    )
    assert len(cliente.get("/autores", params={"q": "Cort"}).json()) == 1
    assert len(cliente.get("/autores", params={"q": "Julio"}).json()) == 1

    cliente.post(
        "/libros",
        json={"titulo": "El nombre de la rosa", "titulo_original": "Il nome della rosa"},
        headers=CLAVE,
    )
    assert len(cliente.get("/libros", params={"q": "nome della"}).json()) == 1

    libro = cliente.post("/libros", json={"titulo": "Prestado"}, headers=CLAVE).json()
    cliente.post(
        "/ejemplares",
        json={"libro_id": libro["id"], "en_prestamo": True, "prestado_a": "Marta"},
        headers=CLAVE,
    )
    assert len(cliente.get("/ejemplares", params={"q": "Marta"}).json()) == 1
    assert len(cliente.get("/ejemplares", params={"q": "Nadie"}).json()) == 0


def test_filtros_de_listado(cliente):
    cliente.post("/libros", json={"titulo": "El Quijote", "idioma": "es"}, headers=CLAVE)
    cliente.post("/libros", json={"titulo": "Hamlet", "idioma": "en"}, headers=CLAVE)

    assert len(cliente.get("/libros", params={"q": "Quij"}).json()) == 1
    assert len(cliente.get("/libros", params={"idioma": "en"}).json()) == 1
    assert len(cliente.get("/libros").json()) == 2


def test_el_contenedor_sigue_siendo_un_geopackage(cliente):
    """Escribir por la API no debe romper el archivo para QGIS."""
    cliente.post("/libros", json={"titulo": "Marca de tiempo"}, headers=CLAVE)

    conn = sqlite3.connect(GPKG)
    try:
        assert conn.execute("PRAGMA application_id").fetchone()[0] == 1196444487
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10300
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        # gpkg_contents.last_change debe haberse actualizado al escribir.
        cambio = conn.execute(
            "SELECT last_change FROM gpkg_contents WHERE table_name = 'libros'"
        ).fetchone()[0]
        assert cambio and cambio.endswith("Z")

        # Las capas espaciales siguen registradas.
        capas = {f[0] for f in conn.execute("SELECT table_name FROM gpkg_geometry_columns")}
        assert capas == {"paises", "ubicaciones"}
    finally:
        conn.close()
