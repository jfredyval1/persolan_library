"""Acceso a SQLite/GeoPackage.

El esquema es de solo lectura para este código: se consulta, nunca se declara.
Quien crea las tablas son los scripts de sql/, para que el archivo siga siendo
un GeoPackage 1.3.0 válido.
"""

import sqlite3
from collections.abc import Iterator

from .config import GPKG_PATH

_wal_configurado = False


def conectar() -> sqlite3.Connection:
    """Abre una conexión con los PRAGMAs que el esquema da por supuestos."""
    global _wal_configurado

    if not GPKG_PATH.exists():
        raise FileNotFoundError(
            f"No se encuentra el GeoPackage en {GPKG_PATH}. "
            "Créalo con los scripts de sql/ o define BIBLIOTECA_GPKG."
        )

    # check_same_thread=False porque FastAPI puede resolver la dependencia en un
    # hilo del pool y ejecutar después un endpoint async en el hilo del bucle de
    # eventos. Es seguro: cada petición tiene su propia conexión y la usa de
    # forma secuencial, nunca dos hilos a la vez.
    conn = sqlite3.connect(
        GPKG_PATH, timeout=5.0, isolation_level="DEFERRED", check_same_thread=False
    )
    conn.row_factory = sqlite3.Row

    # Crítico: foreign_keys es un ajuste POR CONEXIÓN. La línea de 01_schema.sql
    # no persiste en el archivo, así que sin esto las claves foráneas del
    # esquema simplemente no se aplican.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")

    if not _wal_configurado:
        # WAL sí persiste en el archivo; basta hacerlo una vez por proceso.
        # Permite que QGIS tenga el .gpkg abierto mientras la API escribe.
        conn.execute("PRAGMA journal_mode = WAL")
        _wal_configurado = True

    return conn


def obtener_db() -> Iterator[sqlite3.Connection]:
    """Dependencia de FastAPI: una conexión por petición."""
    conn = conectar()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def marcar_cambio(conn: sqlite3.Connection, tabla: str) -> None:
    """Actualiza gpkg_contents.last_change, como pide la especificación GeoPackage.

    Es lo que hace que QGIS y otros clientes se enteren de que la capa cambió.
    """
    conn.execute(
        "UPDATE gpkg_contents "
        "SET last_change = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
        "WHERE table_name = ?",
        (tabla,),
    )
