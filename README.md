# Biblioteca personal

Catálogo de una biblioteca doméstica sobre un **GeoPackage** (SQLite): el
esquema SQL de los libros y sus ejemplares, más una **API FastAPI** que los da
de alta a partir del ISBN, para no escribir un `INSERT` por libro.

```
sql/     esquema del GeoPackage y semillas (países, Dewey)
api/     API FastAPI: CRUD, alta por ISBN, importación en lote
tests/   27 pruebas, sin dependencia de la red
```

---

## Qué hace

El trabajo manual de catalogar no está en el `INSERT`, sino en teclear título,
autor, editorial, año y páginas de cada libro. La API lo resuelve así:

**Alta por ISBN.** `POST /libros/desde-isbn` consulta Open Library — y Google
Books si allí no aparece —, crea el libro y **crea o reutiliza el autor y la
editorial**, resolviendo las tablas puente. Si le indicas una balda, añade
también el ejemplar. `GET /lookup/{isbn}` hace lo mismo sin guardar nada, para
mirar la ficha antes de decidir.

**Importación en lote.** Una lista de ISBNs (`POST /importar/isbns`) o un CSV
(`POST /importar/csv`), que además admite filas sin ISBN para los libros que
ninguna fuente conoce. Devuelven un informe fila a fila —
`creado` / `duplicado` / `no_encontrado` / `error` — y **cada fila se confirma
por separado**: un fallo en la fila 40 no deshace las 39 anteriores.

**CRUD completo** sobre las 10 tablas, con las restricciones del esquema
traducidas a respuestas HTTP con sentido: ISBN repetido → 409, referencia
inexistente → 400, ejemplar prestado sin destinatario → 422.

**El GeoPackage sigue siendo válido.** La API nunca altera el esquema: lo crean
los scripts de `sql/`. Actualiza `gpkg_contents.last_change` en cada escritura,
como pide la especificación, para que QGIS se entere de los cambios.

### Decisiones de diseño

- **Sin ORM.** `sqlite3` de la biblioteca estándar con una capa fina de
  repositorio. Un ORM sobre un GeoPackage invita a que una migración altere
  tablas y deje `gpkg_contents` / `gpkg_geometry_columns` desincronizados,
  rompiendo el archivo para QGIS. Aquí el esquema es de solo lectura para el
  código: se consulta, no se declara.
- **Cuatro dependencias**: FastAPI, uvicorn, Pydantic y httpx.
- **Swagger UI como interfaz.** No hay frontend propio: `/docs` ya da
  formularios para todo.

---

## Puesta en marcha

### Requisitos

- Python **3.10 o superior** (probado en 3.13)
- `sqlite3` en la línea de comandos
- Conexión a internet para el alta por ISBN (el resto de la API funciona sin ella)

### 1. Clonar e instalar

```bash
git clone <url-del-repositorio> Biblioteca_Personal
cd Biblioteca_Personal

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> **Si `python3 -m venv` falla con «ensurepip is not available»** te falta el
> paquete del sistema: `sudo apt install python3-venv python3-pip`.
> Sin permisos de administrador, el zipapp oficial de PyPA hace el mismo
> trabajo:
>
> ```bash
> python3 -m venv --without-pip .venv
> curl -sSL https://bootstrap.pypa.io/pip/pip.pyz -o /tmp/pip.pyz
> .venv/bin/python3 /tmp/pip.pyz install -r requirements.txt
> ```

### 2. Preparar la base

El repositorio incluye `sql/gpkg/biblioteca.gpkg` **con el esquema ya creado**.
Solo faltan las semillas de `paises` y `dewey`, que las claves foráneas
necesitan para tener a qué apuntar:

```bash
sqlite3 sql/gpkg/biblioteca.gpkg < sql/03_seed_paises.sql   # 249 países ISO 3166-1
sqlite3 sql/gpkg/biblioteca.gpkg < sql/04_seed_dewey.sql    # 10 clases + 90 divisiones CDD
```

Usan `INSERT OR IGNORE`, así que puedes reejecutarlas sin efectos.

<details>
<summary><b>Empezar con una base vacía, desde cero</b></summary>

Si prefieres tu propia base sin los datos que vienen en el repo — por ejemplo
tus estanterías son otras — aparta el archivo y ejecuta los cinco scripts en
orden sobre uno nuevo:

```bash
mv sql/gpkg/biblioteca.gpkg sql/gpkg/biblioteca.gpkg.original

sqlite3 sql/gpkg/biblioteca.gpkg < sql/00_gpkg_init.sql             # contenedor GeoPackage 1.3.0
sqlite3 sql/gpkg/biblioteca.gpkg < sql/01_schema.sql                # las 10 tablas de negocio
sqlite3 sql/gpkg/biblioteca.gpkg < sql/02_gpkg_register_layers.sql  # registro de capas
sqlite3 sql/gpkg/biblioteca.gpkg < sql/03_seed_paises.sql
sqlite3 sql/gpkg/biblioteca.gpkg < sql/04_seed_dewey.sql
```

Los tres primeros **fallan con «table already exists» si el archivo ya tiene el
esquema**: son para crear una base nueva, no para actualizar una existente.

Después registra tus estanterías con `POST /ubicaciones`, una por balda.
</details>

### 3. Arrancar

```bash
BIBLIOTECA_API_KEY=elige-una-clave \
  .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Abre **<http://127.0.0.1:8000/docs>**, pulsa **Authorize**, pega la clave y ya
puedes operar desde los formularios. `GET /salud` confirma qué archivo está
usando la API y cuántos libros lleva.

### Variables de entorno

| Variable | Por defecto | Para qué |
|---|---|---|
| `BIBLIOTECA_GPKG` | `sql/gpkg/biblioteca.gpkg` | Ruta del GeoPackage. Útil para probar sobre una copia. |
| `BIBLIOTECA_API_KEY` | *(sin definir)* | Clave de escritura. **Sin ella la API arranca en solo lectura** y toda escritura responde 503. |
| `BIBLIOTECA_PAUSA_LOTE` | `0.5` | Segundos entre consultas externas durante una importación. |

---

## Cómo se cataloga

### Un libro con ISBN — el camino normal

```bash
curl -X POST localhost:8000/libros/desde-isbn \
  -H 'X-API-Key: elige-una-clave' -H 'Content-Type: application/json' \
  -d '{"isbn":"978-0-14-032872-1","ubicacion_id":1,"estado_fisico":"bueno"}'
```

Devuelve la ficha completa: libro, autor y editorial recién creados, y el
ejemplar en la balda 1. Los guiones del ISBN dan igual, y un ISBN mal tecleado
se rechaza por su dígito de control antes de salir a la red.

### Varios de golpe

```bash
curl -X POST localhost:8000/importar/isbns \
  -H 'X-API-Key: elige-una-clave' -H 'Content-Type: application/json' \
  -d '{"isbns":["9788420412146","9780061120084"],"ubicacion_id":2,"estado_fisico":"bueno"}'
```

### Desde un CSV

`POST /importar/csv`, con cabecera. Las filas con `isbn` se resuelven contra las
fuentes externas; las que no lo traen se dan de alta con las columnas que haya:

```csv
isbn,titulo,autor,editorial,anio,paginas,idioma,ubicacion_id,estado_fisico,notas
9788437604947,,,,,,,3,bueno,
,Rayuela,Julio Cortázar,Sudamericana,1963,736,es,4,regular,edición de bolsillo
```

Varios autores en la misma fila se separan con `;`.

### Un libro sin ISBN

`POST /libros` acepta `autor_ids` y `genero_ids` y resuelve las tablas puente
por ti. En `PATCH /libros/{id}`, omitir esas listas deja la relación intacta;
enviarlas la reemplaza entera.

### Prestar y devolver

```bash
curl -X PATCH localhost:8000/ejemplares/1 -H 'X-API-Key: …' \
  -H 'Content-Type: application/json' -d '{"en_prestamo":true,"prestado_a":"Marta"}'
```

---

## Endpoints

| Recurso | Endpoints |
|---|---|
| **Alta por ISBN** | `GET /lookup/{isbn}` · `POST /libros/desde-isbn` |
| **Importación** | `POST /importar/isbns` · `POST /importar/csv` |
| **Libros** | `GET` `POST` `/libros` · `GET` `PATCH` `DELETE` `/libros/{id}` |
| **Ejemplares** | `GET` `POST` `/ejemplares` · `GET` `PATCH` `DELETE` `/ejemplares/{id}` |
| **Catálogos** | Mismo juego para `/paises`, `/dewey`, `/generos`, `/autores`, `/editoriales`, `/ubicaciones` |
| **Estado** | `GET /salud` |

Los listados aceptan `q`, `limit` y `offset`. El filtro `q` mira varias
columnas a la vez, las que uno buscaría de forma natural: a un autor por nombre
o apellidos, a un libro por título, título original o ISBN, a un ejemplar por
sus notas o por a quién está prestado. Además, `/libros` acepta `editorial_id`
e `idioma`, y `/ejemplares` acepta `libro_id`, `ubicacion_id` y `en_prestamo`.

**Las lecturas son abiertas; toda escritura exige la cabecera `X-API-Key`.**

---

## Pruebas

```bash
.venv/bin/python3 -m pytest tests/ -q
```

Construyen la base desde los propios scripts de `sql/` — así validan también que
siguen siendo correctos — y simulan las fuentes externas, por lo que no dependen
de la red. Cubren que las claves foráneas están activas, que la regla de
préstamo se respeta, que cada fila de una importación es independiente, y que
tras escribir por la API el archivo sigue siendo un GeoPackage válido.

---

## Notas importantes

1. **Sin roles**: SQLite no tiene usuarios. La única protección es la clave de
   `X-API-Key`, exigida solo en las escrituras, y escuchar en `127.0.0.1`. No
   expongas el puerto sin poner algo delante.

2. **`PRAGMA foreign_keys` es por conexión**: la línea de `01_schema.sql` no
   persiste en el archivo. La API lo activa en cada conexión; si consultas el
   `.gpkg` con otra herramienta, recuerda hacerlo tú o las claves foráneas no se
   aplicarán.

3. **Modo WAL**: la API lo activa para poder escribir con el `.gpkg` abierto en
   QGIS. Genera ficheros `-wal` y `-shm` junto al GeoPackage (ya ignorados en
   `.gitignore`).

4. **Geometrías**: `sqlite3` puro no calcula el blob GeoPackage a partir de WKT
   o GeoJSON. La API no toca `paises.geom` ni `ubicaciones.geom`; para cargarlas
   usa `ogr2ogr`, QGIS (DB Manager) o Python:
   ```python
   gdf.to_file("biblioteca.gpkg", layer="ubicaciones", driver="GPKG")
   ```

5. **Sin componente espacial**: si prefieres prescindir de los mapas, ejecuta
   solo `01_schema.sql` y las semillas sobre un `.db`/`.sqlite` normal. El
   esquema y la API funcionan igual.

6. **Regla de negocio**: `ejemplares` incluye
   `CHECK (en_prestamo = 0 OR prestado_a IS NOT NULL)` — un ejemplar marcado
   como prestado siempre debe tener a quién. La API lo valida antes de tocar la
   base y devuelve 422, también en los `PATCH` que dejarían la fila incoherente.

7. **Los datos externos no son perfectos**: el nombre del autor se parte por el
   primer espacio (`"Miguel de Cervantes Saavedra"` → nombre `Miguel`, apellidos
   `de Cervantes Saavedra`), y cuando la fuente solo da el año, la fecha se
   completa con el 1 de enero. Repasa y corrige con `PATCH` lo que haga falta.

8. **Google Books limita el uso anónimo** con `429`. Si una fuente no responde,
   la API devuelve 503 en vez de dar el ISBN por inexistente: «no lo encuentro»
   y «no he podido preguntar» no son lo mismo, y confundirlos daría por perdido
   un libro que sí está catalogado.

9. **La clasificación Dewey de la semilla llega a las divisiones** (10 clases +
   90 divisiones). Las 1000 secciones quedan fuera, pero la notación exacta de
   cada libro se guarda íntegra en `libros.dewey_codigo_completo`: no se pierde
   precisión, `dewey_categoria_id` solo agrupa para poder navegar.
