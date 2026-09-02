#!/bin/sh
# Prepara el GeoPackage y cede el control al comando del contenedor.
#
# La base no puede construirse durante el `docker build` porque no vive en la
# imagen: está en el directorio compartido con el host, que solo existe cuando
# el contenedor ya está en marcha. De ahí que este paso sea de arranque.
set -eu

GPKG="${BIBLIOTECA_GPKG:-/datos/biblioteca.gpkg}"
DIRECTORIO=$(dirname "$GPKG")

# El orden importa: el contenedor GeoPackage, luego el esquema, luego el
# registro de capas y por último las dos semillas de catálogos.
SCRIPTS="00_gpkg_init 01_schema 02_gpkg_register_layers 03_seed_paises 04_seed_dewey"

mkdir -p "$DIRECTORIO"

# Si el directorio está en el mismo sistema de archivos que /, nadie ha montado
# nada ahí. Es un aviso, no un error: el contenedor arranca igual, pero conviene
# enterarse antes de catalogar cien libros que se van a ir con el contenedor.
if [ "$(stat -c %d "$DIRECTORIO")" = "$(stat -c %d /)" ]; then
    echo "AVISO: $DIRECTORIO no es un volumen montado." >&2
    echo "       El GeoPackage vivirá dentro del contenedor y se perderá al borrarlo." >&2
    echo "       Monta el directorio del host:  -v \"\$PWD/datos:/datos\"" >&2
fi

if [ -f "$GPKG" ]; then
    echo "GeoPackage existente, se usa tal cual: $GPKG"
else
    echo "No hay GeoPackage en $GPKG; se construye desde los scripts de sql/."

    # Se construye sobre un nombre provisional y se renombra al terminar. Si un
    # script falla a medias, el directorio compartido no se queda con una base
    # incompleta que el siguiente arranque daría por buena (existe -> se usa).
    PARCIAL="$GPKG.parcial"
    rm -f "$PARCIAL" "$PARCIAL-wal" "$PARCIAL-shm"
    trap 'rm -f "$PARCIAL" "$PARCIAL-wal" "$PARCIAL-shm"' EXIT INT TERM

    for nombre in $SCRIPTS; do
        echo "  sql/$nombre.sql"
        sqlite3 "$PARCIAL" < "/app/sql/$nombre.sql"
    done

    trap - EXIT INT TERM
    mv "$PARCIAL" "$GPKG"   # mismo directorio: el renombrado es atómico
    echo "GeoPackage creado: $GPKG"
fi

exec "$@"
