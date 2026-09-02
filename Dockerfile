# syntax=docker/dockerfile:1
#
# Backend de la biblioteca personal: la API FastAPI más los scripts que
# construyen el GeoPackage.
#
# El .gpkg NO vive en la imagen ni en el contenedor: se crea, al arrancar, en
# el directorio montado en /datos, para que el host lo pueda abrir en QGIS
# mientras la API sigue en marcha (el esquema usa WAL precisamente para eso).
#
#   docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -t biblioteca:latest .
#   docker run -it -d -p 127.0.0.1:8000:8000 --name back_biblioteca \
#              -v "$PWD/datos:/datos" --env-file .env \
#              --restart unless-stopped biblioteca:latest

# ---------------------------------------------------------------------------
# Etapa 1: dependencias
# ---------------------------------------------------------------------------
# Se instalan en un venv propio que después se copia entero. Así pip y su
# caché se quedan en esta etapa y no engordan la imagen final.
FROM python:3.13-slim AS dependencias

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiar solo requirements antes que el código: mientras no cambien las
# versiones, esta capa se reaprovecha y el build no vuelve a bajar nada.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Etapa 2: imagen de ejecución
# ---------------------------------------------------------------------------
FROM python:3.13-slim

# sqlite3 en línea de comandos: es lo que usa el entrypoint para levantar el
# GeoPackage con los cinco scripts de sql/, igual que el README a mano. De
# paso queda disponible para inspeccionar la base con `docker exec`.
RUN apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 \
 && rm -rf /var/lib/apt/lists/*

# El contenedor escribe en un directorio del host (/datos), así que su usuario
# tiene que coincidir con el dueño de ese directorio o el .gpkg no se podrá
# crear. 1000:1000 es el primer usuario en la mayoría de instalaciones Linux;
# si el tuyo es otro:  docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) .
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "$GID" biblioteca \
 && useradd --uid "$UID" --gid "$GID" --no-create-home biblioteca

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BIBLIOTECA_GPKG=/datos/biblioteca.gpkg

COPY --from=dependencias /opt/venv /opt/venv

WORKDIR /app

# El código va aparte de los scripts SQL a propósito: tocar api/ no invalida
# la capa de sql/, que arrastra los 2 MB de fronteras de 03_seed_paises.sql.
COPY sql/ ./sql/
COPY static/ ./static/
COPY api/ ./api/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Punto de montaje del GeoPackage. Se crea con el dueño correcto para el caso
# en que se monte un volumen con nombre (Docker hereda de aquí los permisos);
# con un bind mount manda lo que diga el host.
RUN mkdir -p /datos && chown biblioteca:biblioteca /datos

USER biblioteca

EXPOSE 8000

# /salud abre el GeoPackage y cuenta los libros: comprueba de una vez que el
# proceso responde y que la base sigue accesible.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=4)"

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
