-- Inicialización del contenedor GeoPackage (OGC GeoPackage 1.3.0)
-- Ejecutar primero, sobre un archivo nuevo:
--   sqlite3 biblioteca.gpkg < sql/00_gpkg_init.sql

PRAGMA application_id = 1196444487; -- 0x47504B47 ("GPKG" en ASCII)
PRAGMA user_version   = 10300;      -- versión de especificación 1.3.0

CREATE TABLE gpkg_spatial_ref_sys (
    srs_name                  TEXT    NOT NULL,
    srs_id                    INTEGER NOT NULL PRIMARY KEY,
    organization               TEXT    NOT NULL,
    organization_coordsys_id   INTEGER NOT NULL,
    definition                 TEXT    NOT NULL,
    description                 TEXT
);

CREATE TABLE gpkg_contents (
    table_name    TEXT     NOT NULL PRIMARY KEY,
    data_type     TEXT     NOT NULL,
    identifier    TEXT     UNIQUE,
    description   TEXT     DEFAULT '',
    last_change   DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    min_x         DOUBLE,
    min_y         DOUBLE,
    max_x         DOUBLE,
    max_y         DOUBLE,
    srs_id        INTEGER,
    CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);

CREATE TABLE gpkg_geometry_columns (
    table_name          TEXT    NOT NULL,
    column_name         TEXT    NOT NULL,
    geometry_type_name  TEXT    NOT NULL,
    srs_id               INTEGER NOT NULL,
    z                     TINYINT NOT NULL,
    m                     TINYINT NOT NULL,
    CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
    CONSTRAINT uk_gc_table  UNIQUE (table_name),
    CONSTRAINT fk_gc_tn     FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
    CONSTRAINT fk_gc_srs    FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);

-- Filas obligatorias del estándar GeoPackage (Undefined Cartesian / Undefined geographic)
INSERT INTO gpkg_spatial_ref_sys (srs_name, srs_id, organization, organization_coordsys_id, definition, description) VALUES
    ('Undefined Cartesian SRS', -1, 'NONE', -1, 'undefined', 'Sistema cartesiano local (usado por ubicaciones, plano interno de la casa)'),
    ('Undefined geographic SRS', 0, 'NONE',  0, 'undefined', 'Sistema geográfico no definido');

-- WGS 84, para las geometrías de países
INSERT INTO gpkg_spatial_ref_sys (srs_name, srs_id, organization, organization_coordsys_id, definition, description) VALUES
    ('WGS 84', 4326, 'EPSG', 4326,
     'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]',
     'longitud/latitud WGS 84');
