"""Fixtures de prueba.

La base se construye desde los propios scripts de sql/, no copiando el .gpkg
real: así cada ejecución valida también que esos scripts siguen siendo válidos.
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="biblioteca-test-"))
PLANTILLA = _TMP / "plantilla.gpkg"
GPKG = _TMP / "prueba.gpkg"

SCRIPTS = [
    "00_gpkg_init.sql",
    "01_schema.sql",
    "02_gpkg_register_layers.sql",
    "03_seed_paises.sql",
    "04_seed_dewey.sql",
]

for nombre in SCRIPTS:
    conn = sqlite3.connect(PLANTILLA)
    conn.executescript((RAIZ / "sql" / nombre).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()

# api.config lee el entorno al importarse: hay que fijarlo antes.
os.environ["BIBLIOTECA_GPKG"] = str(GPKG)
os.environ["BIBLIOTECA_API_KEY"] = "clave-de-prueba"
os.environ["BIBLIOTECA_PAUSA_LOTE"] = "0"

CLAVE = {"X-API-Key": "clave-de-prueba"}


@pytest.fixture
def cliente():
    from fastapi.testclient import TestClient

    from api.main import app

    for sufijo in ("", "-wal", "-shm"):
        Path(str(GPKG) + sufijo).unlink(missing_ok=True)
    shutil.copy(PLANTILLA, GPKG)

    with TestClient(app) as c:
        yield c


@pytest.fixture
def conexion():
    return sqlite3.connect(GPKG)


def crear_modulo(cliente, *, nombre="central", habitacion="sala", columna=1, fila=1) -> dict:
    """Da de alta un mueble entero y devuelve sus tres piezas.

    Colocar un libro cuesta tres altas —el punto en el plano, el mueble y el
    casillero— porque son tres cosas distintas; casi todas las pruebas solo
    necesitan el `modulo`, así que se hace aquí una vez.
    """
    ubicacion = cliente.post(
        "/ubicaciones", json={"nombre": nombre, "habitacion": habitacion}, headers=CLAVE
    ).json()
    estanteria = cliente.post(
        "/estanterias",
        json={"ubicacion_id": ubicacion["id"], "nombre": nombre, "tipo": "biblioteca"},
        headers=CLAVE,
    ).json()
    modulo = cliente.post(
        "/modulos",
        json={"estanteria_id": estanteria["id"], "columna": columna, "fila": fila},
        headers=CLAVE,
    ).json()
    return {"ubicacion": ubicacion, "estanteria": estanteria, "modulo": modulo}
