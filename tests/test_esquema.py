"""Invariantes del esquema y del contenedor GeoPackage.

Esto es lo que no se puede comprobar mirando: una clave foránea que deja de
aplicarse, un `CHECK` que ya no salta o un GeoPackage que QGIS no abre no dan
ningún error visible el día que se rompen. Se descubren meses después, con los
datos ya sucios.

Además, como el `.gpkg` no está versionado, los scripts de `sql/` **son** la
base de datos: `conftest.py` los ejecuta en cada corrida, así que estas pruebas
validan de paso que siguen siendo correctos.
"""

import sqlite3
import struct

from .conftest import CLAVE, GPKG, crear_modulo


# ------------------------------------------------------- el contenedor GeoPackage
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

def test_el_gpkg_es_valido_con_el_mobiliario(cliente):
    """Dar de alta muebles y casilleros no debe romper el archivo para QGIS."""
    crear_modulo(cliente)

    conn = sqlite3.connect(GPKG)
    try:
        assert conn.execute("PRAGMA application_id").fetchone()[0] == 1196444487
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10300
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        # `estanterias` y `modulos` son atributos, no capas: no tienen geometría
        # y la única espacial del interior de la casa sigue siendo `ubicaciones`.
        registradas = dict(
            conn.execute("SELECT table_name, data_type FROM gpkg_contents")
        )
        assert registradas["estanterias"] == "attributes"
        assert registradas["modulos"] == "attributes"
        assert registradas["ubicaciones"] == "features"

        capas = {f[0] for f in conn.execute("SELECT table_name FROM gpkg_geometry_columns")}
        assert capas == {"paises", "ubicaciones"}

        # Toda tabla registrada en gpkg_contents debe existir de verdad.
        reales = {f[0] for f in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        assert set(registradas) <= reales
    finally:
        conn.close()

def test_la_capa_de_paises_es_espacial_desde_la_semilla(cliente, conexion):
    """Las geometrías vienen en el propio `03_seed_paises.sql`.

    Es lo que permite abrir el mapa en QGIS nada más crear la base, sin pasar
    por ogr2ogr: sqlite3 no sabe construir un blob GeoPackage, pero sí insertar
    uno ya construido.
    """
    total, con_geom = conexion.execute("SELECT COUNT(*), COUNT(geom) FROM paises").fetchone()
    assert (total, con_geom) == (250, 239)

    blob = conexion.execute(
        "SELECT geom FROM paises WHERE codigo_iso = 'ES'"
    ).fetchone()[0]
    assert blob[:2] == b"GP"                                # magic
    assert blob[2] == 0                                     # versión de la cabecera
    assert blob[3] & 0b0000_0001                            # little-endian
    assert (blob[3] >> 1) & 0b111 == 1                      # envelope [minx,maxx,miny,maxy]
    assert struct.unpack("<i", blob[4:8])[0] == 4326        # SRS declarado

    # Tras la cabecera (8) y el envelope (32) empieza el WKB.
    assert blob[40] == 1                                    # WKB little-endian
    assert struct.unpack("<I", blob[41:45])[0] == 6         # 6 = MultiPolygon

    # El tipo declarado en el catálogo y el real deben coincidir.
    assert conexion.execute(
        "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name = 'paises'"
    ).fetchone()[0] == "MULTIPOLYGON"

    # Sin bbox en gpkg_contents, QGIS no sabe a dónde encuadrar el mapa.
    min_x, min_y, max_x, max_y = conexion.execute(
        "SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name = 'paises'"
    ).fetchone()
    assert -180 <= min_x < max_x <= 180
    assert -90 <= min_y < max_y <= 90


# ---------------------------------------------- claves foráneas y reglas del esquema
def test_las_claves_foraneas_estan_activas(cliente):
    """Sin PRAGMA foreign_keys=ON esto devolvería 201 en vez de 400."""
    libro = cliente.post("/libros", json={"titulo": "Suelto"}, headers=CLAVE).json()
    resp = cliente.post(
        "/ejemplares", json={"libro_id": libro["id"], "modulo_id": 9999}, headers=CLAVE
    )
    assert resp.status_code == 400
    assert "Referencia inexistente" in resp.json()["detail"]

def test_un_modulo_exige_una_estanteria_existente(cliente):
    resp = cliente.post(
        "/modulos", json={"estanteria_id": 9999, "columna": 1, "fila": 1}, headers=CLAVE
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

def test_un_punto_del_plano_es_de_un_solo_mueble(cliente):
    """`estanterias.ubicacion_id` es UNIQUE: un punto, una estantería."""
    mueble = crear_modulo(cliente)
    resp = cliente.post(
        "/estanterias",
        json={"ubicacion_id": mueble["ubicacion"]["id"], "nombre": "otra"},
        headers=CLAVE,
    )
    assert resp.status_code == 409

def test_no_hay_dos_casilleros_en_la_misma_celda(cliente):
    mueble = crear_modulo(cliente, columna=2, fila=3)
    resp = cliente.post(
        "/modulos",
        json={"estanteria_id": mueble["estanteria"]["id"], "columna": 2, "fila": 3},
        headers=CLAVE,
    )
    assert resp.status_code == 409

def test_borrar_la_ubicacion_arrastra_mueble_y_casilleros(cliente):
    """ON DELETE CASCADE hacia abajo, pero no si aún hay libros colocados."""
    mueble = crear_modulo(cliente)
    libro = cliente.post("/libros", json={"titulo": "Anclado"}, headers=CLAVE).json()
    cliente.post(
        "/ejemplares",
        json={"libro_id": libro["id"], "modulo_id": mueble["modulo"]["id"]},
        headers=CLAVE,
    )

    # El casillero está ocupado: la cascada choca con la FK de ejemplares.
    assert cliente.delete(
        f"/ubicaciones/{mueble['ubicacion']['id']}", headers=CLAVE
    ).status_code == 400

    # Vaciado el casillero, el mueble entero se va de una pieza.
    cliente.delete(f"/ejemplares/{cliente.get('/ejemplares').json()[0]['id']}", headers=CLAVE)
    assert cliente.delete(
        f"/ubicaciones/{mueble['ubicacion']['id']}", headers=CLAVE
    ).status_code == 204
    assert cliente.get("/estanterias").json() == []
    assert cliente.get("/modulos").json() == []


# ------------------------------------------------------------------ localización


# --------------------------------------------------------- la cadena de localización
def test_un_ejemplar_se_localiza_con_un_solo_join_encadenado(cliente, conexion):
    mueble = crear_modulo(cliente, nombre="escalera", habitacion="pasillo", columna=3, fila=2)
    libro = cliente.post("/libros", json={"titulo": "Rayuela"}, headers=CLAVE).json()
    ejemplar = cliente.post(
        "/ejemplares",
        json={"libro_id": libro["id"], "modulo_id": mueble["modulo"]["id"]},
        headers=CLAVE,
    ).json()

    conexion.row_factory = sqlite3.Row
    fila = conexion.execute(
        "SELECT l.titulo, m.columna, m.fila, e.nombre AS estanteria, "
        "       u.nombre AS ubicacion, u.habitacion "
        "FROM ejemplares ej "
        "JOIN libros      l ON l.id = ej.libro_id "
        "JOIN modulos     m ON m.id = ej.modulo_id "
        "JOIN estanterias e ON e.id = m.estanteria_id "
        "JOIN ubicaciones u ON u.id = e.ubicacion_id "
        "WHERE ej.id = ?",
        (ejemplar["id"],),
    ).fetchone()

    assert dict(fila) == {
        "titulo": "Rayuela",
        "columna": 3,
        "fila": 2,
        "estanteria": "escalera",
        "ubicacion": "escalera",
        "habitacion": "pasillo",
    }

def test_el_perfil_de_columnas_se_deriva_de_los_modulos(cliente, conexion):
    """Una estantería tipo escalera: columnas de 1, 2 y 3 casilleros."""
    mueble = crear_modulo(cliente, nombre="escalera", columna=1, fila=1)
    estanteria_id = mueble["estanteria"]["id"]
    for columna, filas in ((2, 2), (3, 3)):
        for fila in range(1, filas + 1):
            cliente.post(
                "/modulos",
                json={"estanteria_id": estanteria_id, "columna": columna, "fila": fila},
                headers=CLAVE,
            )

    perfil = conexion.execute(
        "SELECT columnas, modulos, perfil FROM vista_perfil_estanterias "
        "WHERE estanteria_id = ?",
        (estanteria_id,),
    ).fetchone()
    assert perfil == (3, 6, "1,2,3")
