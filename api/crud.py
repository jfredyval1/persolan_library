"""Capa de acceso a datos.

Los nombres de tabla y columna que se interpolan aquí proceden siempre de
constantes del propio código, nunca de la petición; los valores van siempre
como parámetros ligados.
"""

import sqlite3
from datetime import date, datetime
from typing import Any

from .db import marcar_cambio

# Columnas expuestas por la API. Se listan de forma explícita para no arrastrar
# las columnas `geom` (BLOB GeoPackage) en las respuestas JSON.
COLUMNAS: dict[str, list[str]] = {
    "paises": ["codigo_iso", "nombre"],
    "dewey": ["codigo", "descripcion", "nivel", "padre_codigo"],
    "generos": ["id", "nombre", "dewey_relacionado"],
    "autores": ["id", "nombre", "apellidos", "pais_id", "fecha_nacimiento", "fecha_fallecimiento"],
    "editoriales": ["id", "nombre", "pais_id", "ciudad_publicacion"],
    "ubicaciones": ["id", "nombre", "habitacion", "mueble", "nivel_balda", "capacidad_estimada"],
    "libros": [
        "id", "titulo", "titulo_original", "isbn", "idioma",
        "dewey_codigo_completo", "dewey_categoria_id", "fecha_publicacion",
        "fecha_escritura_original", "numero_paginas", "sinopsis",
        "portada_path", "editorial_id",
    ],
    "ejemplares": [
        "id", "libro_id", "estado_fisico", "formato", "fecha_adquisicion",
        "precio_compra", "ubicacion_id", "en_prestamo", "prestado_a", "notas",
    ],
}

# Clave primaria y campo de texto sobre el que actúa el filtro `q`.
CLAVE: dict[str, str] = {"paises": "codigo_iso", "dewey": "codigo"}

# Columnas sobre las que actúa el filtro `q`. Varias por tabla donde buscar por
# una sola sería antinatural: a un autor se le busca por el apellido tanto como
# por el nombre, y a un libro por su título original tanto como por el traducido.
CAMPOS_BUSQUEDA: dict[str, tuple[str, ...]] = {
    "paises": ("nombre",),
    "dewey": ("descripcion", "codigo"),
    "generos": ("nombre",),
    "autores": ("nombre", "apellidos"),
    "editoriales": ("nombre", "ciudad_publicacion"),
    "ubicaciones": ("nombre", "habitacion", "mueble"),
    "libros": ("titulo", "titulo_original", "isbn"),
    "ejemplares": ("notas", "prestado_a"),
}


def clave(tabla: str) -> str:
    return CLAVE.get(tabla, "id")


def _a_sql(valor: Any) -> Any:
    """Adapta valores de Python a tipos que sqlite3 acepta sin avisos."""
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def _seleccion(tabla: str) -> str:
    return ", ".join(COLUMNAS[tabla])


def listar(
    conn: sqlite3.Connection,
    tabla: str,
    *,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    filtros: dict[str, Any] | None = None,
) -> list[dict]:
    sql = f"SELECT {_seleccion(tabla)} FROM {tabla}"
    condiciones: list[str] = []
    params: list[Any] = []

    if q:
        campos = CAMPOS_BUSQUEDA[tabla]
        condiciones.append("(" + " OR ".join(f"{c} LIKE ?" for c in campos) + ")")
        params += [f"%{q}%"] * len(campos)
    for campo, valor in (filtros or {}).items():
        if valor is not None:
            condiciones.append(f"{campo} = ?")
            params.append(_a_sql(valor))

    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += f" ORDER BY {clave(tabla)} LIMIT ? OFFSET ?"
    params += [limit, offset]

    return [dict(f) for f in conn.execute(sql, params)]


def obtener(conn: sqlite3.Connection, tabla: str, id_: Any) -> dict | None:
    fila = conn.execute(
        f"SELECT {_seleccion(tabla)} FROM {tabla} WHERE {clave(tabla)} = ?", (id_,)
    ).fetchone()
    return dict(fila) if fila else None


def crear(conn: sqlite3.Connection, tabla: str, datos: dict) -> dict:
    datos = {k: _a_sql(v) for k, v in datos.items()}
    columnas = ", ".join(datos)
    marcas = ", ".join("?" for _ in datos)
    cur = conn.execute(
        f"INSERT INTO {tabla} ({columnas}) VALUES ({marcas})", list(datos.values())
    )
    marcar_cambio(conn, tabla)

    # Las tablas con clave primaria de texto no usan rowid autoincremental.
    id_ = datos[clave(tabla)] if clave(tabla) in datos else cur.lastrowid
    return obtener(conn, tabla, id_)


def actualizar(conn: sqlite3.Connection, tabla: str, id_: Any, datos: dict) -> dict | None:
    if not datos:
        return obtener(conn, tabla, id_)
    datos = {k: _a_sql(v) for k, v in datos.items()}
    asignaciones = ", ".join(f"{c} = ?" for c in datos)
    cur = conn.execute(
        f"UPDATE {tabla} SET {asignaciones} WHERE {clave(tabla)} = ?",
        [*datos.values(), id_],
    )
    if cur.rowcount == 0:
        return None
    marcar_cambio(conn, tabla)
    return obtener(conn, tabla, id_)


def borrar(conn: sqlite3.Connection, tabla: str, id_: Any) -> bool:
    cur = conn.execute(f"DELETE FROM {tabla} WHERE {clave(tabla)} = ?", (id_,))
    if cur.rowcount:
        marcar_cambio(conn, tabla)
        return True
    return False


# --------------------------------------------------------------------- libros
def reemplazar_relacion(
    conn: sqlite3.Connection, tabla: str, columna: str, libro_id: int, ids: list[int]
) -> None:
    """Deja la tabla puente con exactamente los ids indicados."""
    conn.execute(f"DELETE FROM {tabla} WHERE libro_id = ?", (libro_id,))
    for id_ in dict.fromkeys(ids):  # sin duplicados, conservando el orden
        conn.execute(
            f"INSERT INTO {tabla} (libro_id, {columna}) VALUES (?, ?)", (libro_id, id_)
        )
    marcar_cambio(conn, tabla)


def detalle_libro(conn: sqlite3.Connection, libro_id: int) -> dict | None:
    libro = obtener(conn, "libros", libro_id)
    if libro is None:
        return None

    libro["autores"] = [
        dict(f)
        for f in conn.execute(
            f"SELECT a.{', a.'.join(COLUMNAS['autores'])} FROM autores a "
            "JOIN libro_autor la ON la.autor_id = a.id WHERE la.libro_id = ? "
            "ORDER BY a.apellidos, a.nombre",
            (libro_id,),
        )
    ]
    libro["generos"] = [
        dict(f)
        for f in conn.execute(
            f"SELECT g.{', g.'.join(COLUMNAS['generos'])} FROM generos g "
            "JOIN libro_genero lg ON lg.genero_id = g.id WHERE lg.libro_id = ? "
            "ORDER BY g.nombre",
            (libro_id,),
        )
    ]
    libro["ejemplares"] = [
        dict(f)
        for f in conn.execute(
            f"SELECT {_seleccion('ejemplares')} FROM ejemplares WHERE libro_id = ? ORDER BY id",
            (libro_id,),
        )
    ]
    libro["editorial"] = (
        obtener(conn, "editoriales", libro["editorial_id"])
        if libro["editorial_id"] is not None
        else None
    )
    return libro


# ------------------------------------------------- buscar-o-crear (alta por ISBN)
def buscar_o_crear_editorial(conn: sqlite3.Connection, nombre: str) -> int:
    fila = conn.execute(
        "SELECT id FROM editoriales WHERE nombre = ? COLLATE NOCASE", (nombre,)
    ).fetchone()
    if fila:
        return fila["id"]
    return crear(conn, "editoriales", {"nombre": nombre})["id"]


def partir_nombre(completo: str) -> tuple[str, str | None]:
    """'Roald Dahl' -> ('Roald', 'Dahl'). Sin apellido si es una sola palabra."""
    partes = completo.split()
    if len(partes) == 1:
        return partes[0], None
    return partes[0], " ".join(partes[1:])


def buscar_o_crear_autor(conn: sqlite3.Connection, nombre_completo: str) -> int:
    nombre, apellidos = partir_nombre(nombre_completo)
    fila = conn.execute(
        "SELECT id FROM autores WHERE nombre = ? COLLATE NOCASE "
        "AND IFNULL(apellidos,'') = IFNULL(?,'') COLLATE NOCASE",
        (nombre, apellidos),
    ).fetchone()
    if fila:
        return fila["id"]
    return crear(conn, "autores", {"nombre": nombre, "apellidos": apellidos})["id"]


def libro_por_isbn(conn: sqlite3.Connection, isbn: str) -> dict | None:
    fila = conn.execute(
        f"SELECT {_seleccion('libros')} FROM libros WHERE isbn = ?", (isbn,)
    ).fetchone()
    return dict(fila) if fila else None


def categoria_dewey_existente(conn: sqlite3.Connection, codigo_completo: str | None) -> str | None:
    """Deriva la categoría de los 3 primeros dígitos, solo si esa fila existe."""
    if not codigo_completo:
        return None
    raiz = codigo_completo.split(".")[0].strip()[:3]
    if len(raiz) < 3 or not raiz.isdigit():
        return None
    fila = conn.execute("SELECT codigo FROM dewey WHERE codigo = ?", (raiz,)).fetchone()
    return fila["codigo"] if fila else None
