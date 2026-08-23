-- Registro de las tablas en el catálogo del GeoPackage
-- Ejecutar al final:
--   sqlite3 biblioteca.gpkg < sql/02_gpkg_register_layers.sql

-- Tablas espaciales
INSERT INTO gpkg_contents (table_name, data_type, identifier, description, srs_id) VALUES
    ('paises',      'features', 'paises',      'Países de origen de autores y editoriales', 4326),
    ('ubicaciones', 'features', 'ubicaciones', 'Estanterías / espacio de almacenamiento en casa', -1);

INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) VALUES
    ('paises',      'geom', 'MULTIPOLYGON', 4326, 0, 0),
    ('ubicaciones', 'geom', 'POINT',        -1,   0, 0);

-- Tablas no espaciales, registradas como "attributes" para que QGIS y otros
-- clientes GeoPackage las listen junto a las capas espaciales
INSERT INTO gpkg_contents (table_name, data_type, identifier, description) VALUES
    ('dewey',        'attributes', 'dewey',        'Catálogo jerárquico de clasificación Dewey'),
    ('generos',      'attributes', 'generos',      'Géneros/temas de los libros'),
    ('autores',      'attributes', 'autores',      'Autores'),
    ('editoriales',  'attributes', 'editoriales',  'Editoriales'),
    ('libros',       'attributes', 'libros',       'Obras/ediciones catalogadas'),
    ('libro_autor',  'attributes', 'libro_autor',  'Relación N:M libros-autores'),
    ('libro_genero', 'attributes', 'libro_genero', 'Relación N:M libros-géneros'),
    ('ejemplares',   'attributes', 'ejemplares',   'Copias físicas de cada libro');
