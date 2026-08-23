-- Esquema de negocio: catálogo, ejemplares y ubicaciones
-- Ejecutar después de 00_gpkg_init.sql:
--   sqlite3 biblioteca.gpkg < sql/01_schema.sql
--
-- También es válido sobre un archivo SQLite normal (sin GeoPackage),
-- si en algún momento se decide prescindir del componente espacial.

PRAGMA foreign_keys = ON;

CREATE TABLE paises (
    codigo_iso   TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    geom         BLOB  -- MULTIPOLYGON, SRS 4326 (ver gpkg_geometry_columns)
);

CREATE TABLE dewey (
    codigo        TEXT PRIMARY KEY,
    descripcion   TEXT NOT NULL,
    nivel         TEXT NOT NULL CHECK (nivel IN ('clase','division','seccion')),
    padre_codigo  TEXT REFERENCES dewey(codigo)
);

CREATE TABLE generos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL UNIQUE,
    dewey_relacionado   TEXT REFERENCES dewey(codigo)
);

CREATE TABLE autores (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre               TEXT NOT NULL,
    apellidos            TEXT,
    pais_id              TEXT REFERENCES paises(codigo_iso),
    fecha_nacimiento     DATE,
    fecha_fallecimiento  DATE
);

CREATE TABLE editoriales (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre               TEXT NOT NULL,
    pais_id              TEXT REFERENCES paises(codigo_iso),
    ciudad_publicacion   TEXT
);

CREATE TABLE ubicaciones (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre               TEXT NOT NULL,
    habitacion           TEXT,
    mueble               TEXT,
    nivel_balda          TEXT,
    capacidad_estimada   INTEGER,
    geom                 BLOB  -- POINT, SRS -1 (plano local de la casa)
);

CREATE TABLE libros (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo                      TEXT NOT NULL,
    titulo_original              TEXT,
    isbn                         TEXT UNIQUE,
    idioma                       TEXT,
    dewey_codigo_completo        TEXT,
    dewey_categoria_id           TEXT REFERENCES dewey(codigo),
    fecha_publicacion            DATE,
    fecha_escritura_original     DATE,
    numero_paginas               INTEGER,
    sinopsis                     TEXT,
    portada_path                 TEXT,
    editorial_id                 INTEGER REFERENCES editoriales(id)
);

CREATE TABLE libro_autor (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    libro_id   INTEGER NOT NULL REFERENCES libros(id)  ON DELETE CASCADE,
    autor_id   INTEGER NOT NULL REFERENCES autores(id) ON DELETE CASCADE,
    UNIQUE (libro_id, autor_id)
);

CREATE TABLE libro_genero (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    libro_id    INTEGER NOT NULL REFERENCES libros(id)   ON DELETE CASCADE,
    genero_id   INTEGER NOT NULL REFERENCES generos(id) ON DELETE CASCADE,
    UNIQUE (libro_id, genero_id)
);

CREATE TABLE ejemplares (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    libro_id            INTEGER NOT NULL REFERENCES libros(id) ON DELETE CASCADE,
    estado_fisico       TEXT CHECK (estado_fisico IN ('nuevo','bueno','regular','dañado')),
    formato             TEXT,
    fecha_adquisicion   DATE,
    precio_compra       REAL,
    ubicacion_id        INTEGER REFERENCES ubicaciones(id),
    en_prestamo         INTEGER NOT NULL DEFAULT 0 CHECK (en_prestamo IN (0,1)),
    prestado_a          TEXT,
    notas               TEXT,
    CHECK (en_prestamo = 0 OR prestado_a IS NOT NULL)
);

CREATE INDEX idx_libros_editorial     ON libros(editorial_id);
CREATE INDEX idx_libros_dewey         ON libros(dewey_categoria_id);
CREATE INDEX idx_autores_pais         ON autores(pais_id);
CREATE INDEX idx_editoriales_pais     ON editoriales(pais_id);
CREATE INDEX idx_ejemplares_libro     ON ejemplares(libro_id);
CREATE INDEX idx_ejemplares_ubicacion ON ejemplares(ubicacion_id);
CREATE INDEX idx_ejemplares_prestamo  ON ejemplares(en_prestamo);
