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

-- La localización física se resuelve en tres saltos enteros:
--   ejemplares -> modulos -> estanterias -> ubicaciones
-- Solo el último eslabón tiene geometría. Un ejemplar nunca guarda coordenadas
-- propias ni apunta a `ubicaciones`: su sitio es un casillero concreto.

CREATE TABLE ubicaciones (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre               TEXT NOT NULL,
    habitacion           TEXT,
    geom                 BLOB  -- POINT, SRS -1 (huella del mueble en el plano de la casa)
);

CREATE TABLE estanterias (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    -- UNIQUE: un punto del plano es la huella de un solo mueble.
    ubicacion_id         INTEGER NOT NULL UNIQUE REFERENCES ubicaciones(id) ON DELETE CASCADE,
    nombre               TEXT NOT NULL,
    tipo                 TEXT,  -- 'biblioteca', 'repisa', ...
    ancho_total_cm       REAL CHECK (ancho_total_cm  > 0),
    alto_total_cm        REAL CHECK (alto_total_cm   > 0),
    profundidad_cm       REAL CHECK (profundidad_cm  > 0),
    -- Rotación del mueble respecto al plano de la casa, en grados.
    orientacion_grados   REAL NOT NULL DEFAULT 0
                         CHECK (orientacion_grados >= 0 AND orientacion_grados < 360)
);

-- Un módulo es un casillero. La rejilla es irregular a propósito: cada columna
-- puede tener un número distinto de filas (una estantería tipo escalera), y por
-- eso el hueco se describe fila a fila en vez de con un alto x ancho global.
CREATE TABLE modulos (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    estanteria_id        INTEGER NOT NULL REFERENCES estanterias(id) ON DELETE CASCADE,
    columna              INTEGER NOT NULL CHECK (columna >= 1),
    fila                 INTEGER NOT NULL CHECK (fila    >= 1),
    -- Coordenadas LOCALES en cm desde el ancla del mueble, nunca geográficas:
    -- x hacia el ancho, z hacia el alto. Se combinan con ubicaciones.geom y
    -- estanterias.orientacion_grados solo al dibujar, fuera de la base.
    x_offset_cm          REAL,
    z_offset_cm          REAL,
    ancho_cm             REAL CHECK (ancho_cm       > 0),
    alto_cm              REAL CHECK (alto_cm        > 0),
    profundidad_cm       REAL CHECK (profundidad_cm > 0),
    capacidad_estimada   INTEGER CHECK (capacidad_estimada >= 0),
    UNIQUE (estanteria_id, columna, fila)
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
    modulo_id           INTEGER REFERENCES modulos(id),
    -- Estado de conservación, aparte de estado_fisico: son cosas que se
    -- revisan y se arreglan, no la categoría general de la copia.
    tiene_hongos        INTEGER NOT NULL DEFAULT 0 CHECK (tiene_hongos        IN (0,1)),
    requiere_reparacion INTEGER NOT NULL DEFAULT 0 CHECK (requiere_reparacion IN (0,1)),
    fecha_revision      DATE,
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
CREATE INDEX idx_ejemplares_modulo    ON ejemplares(modulo_id);
CREATE INDEX idx_ejemplares_prestamo  ON ejemplares(en_prestamo);
CREATE INDEX idx_estanterias_ubicacion ON estanterias(ubicacion_id);
CREATE INDEX idx_modulos_estanteria    ON modulos(estanteria_id);

-- El perfil de columnas ("1,2,3,4" = cuatro columnas de 1, 2, 3 y 4 casilleros)
-- no se guarda: se deriva de los módulos dados de alta, para que no puedan
-- contradecirse. Las estanterías sin módulos salen con 0 y perfil NULL.
CREATE VIEW vista_perfil_estanterias AS
SELECT
    e.id                  AS estanteria_id,
    e.nombre              AS estanteria,
    IFNULL(p.columnas, 0) AS columnas,
    IFNULL(p.modulos,  0) AS modulos,
    p.perfil              AS perfil
FROM estanterias e
LEFT JOIN (
    SELECT estanteria_id,
           COUNT(*)             AS columnas,
           SUM(n)               AS modulos,
           group_concat(n, ',') AS perfil
    FROM (
        SELECT estanteria_id, columna, COUNT(*) AS n
        FROM modulos
        GROUP BY estanteria_id, columna
        ORDER BY estanteria_id, columna
    )
    GROUP BY estanteria_id
) p ON p.estanteria_id = e.id;
