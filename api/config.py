"""Configuración leída del entorno, con `.env` como valor por defecto."""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path) -> None:
    """Lee un .env sencillo (CLAVE=valor por línea) al entorno del proceso.

    Se hace a mano en vez de con python-dotenv para no sumar una quinta
    dependencia por doce líneas; el formato que hace falta aquí es trivial.

    Usa setdefault a propósito: **lo que ya esté en el entorno gana**. El .env
    es la comodidad para el día a día, no una imposición, así que se puede
    seguir arrancando con `BIBLIOTECA_API_KEY=otra uvicorn ...` para una prueba
    puntual sin tocar el archivo.
    """
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip("\"'"))


_cargar_env(RAIZ / ".env")

# Ruta al contenedor GeoPackage. Se puede apuntar a una copia para pruebas.
GPKG_PATH = Path(os.environ.get("BIBLIOTECA_GPKG", RAIZ / "sql" / "gpkg" / "biblioteca.gpkg"))

# Clave exigida en la cabecera X-API-Key para cualquier escritura.
# Si no está definida, la API arranca en solo lectura (ver api/security.py).
API_KEY = os.environ.get("BIBLIOTECA_API_KEY") or None

# Segundos de espera entre consultas a las APIs públicas durante una importación.
PAUSA_ENTRE_CONSULTAS = float(os.environ.get("BIBLIOTECA_PAUSA_LOTE", "0.5"))

# Clave de Google Books. Sin ella la API responde 429 a TODO: el uso anónimo
# tiene cuota cero, no "cuota pequeña". Se saca gratis en console.cloud.google.com
# (habilitar «Books API» y crear una credencial de tipo clave de API).
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") or None

TIMEOUT_HTTP = 10.0

# Reintentos por fuente ante fallos pasajeros. Google Books devuelve 503
# "Service temporarily unavailable" de forma errática —medido en torno al 40 %
# de las peticiones, sin relación con el ritmo—, así que sin reintentos una
# importación en lote deja filas caídas al azar.
REINTENTOS_FUENTE = int(os.environ.get("BIBLIOTECA_REINTENTOS", "3"))
ESPERA_REINTENTO = float(os.environ.get("BIBLIOTECA_ESPERA_REINTENTO", "0.5"))
