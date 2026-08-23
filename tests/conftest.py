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
