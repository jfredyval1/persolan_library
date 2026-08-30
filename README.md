# Biblioteca personal

Catálogo de una biblioteca doméstica sobre un **GeoPackage** (SQLite): el
esquema SQL de los libros y sus ejemplares, más una **API FastAPI** que los da
de alta a partir del ISBN, para no escribir un `INSERT` por libro.

```
sql/     esquema del GeoPackage y semillas (países con geometría, Dewey)
api/     API FastAPI: CRUD, alta por ISBN, importación en lote
tests/   27 pruebas de esquema y de alta por ISBN, sin red
```

---

## Qué hace

El trabajo manual de catalogar no está en el `INSERT`, sino en teclear título,
autor, editorial, año y páginas de cada libro. La API lo resuelve así:

**Alta por ISBN.** `POST /libros/desde-isbn` consulta Open Library — y Google
Books si allí no aparece —, crea el libro y **crea o reutiliza el autor y la
editorial**, resolviendo las tablas puente. Si le indicas un casillero, añade
también el ejemplar. `GET /lookup/{isbn}` hace lo mismo sin guardar nada, para
mirar la ficha antes de decidir.

**Importación en lote.** Una lista de ISBNs (`POST /importar/isbns`) o un CSV
(`POST /importar/csv`), que además admite filas sin ISBN para los libros que
ninguna fuente conoce. Devuelven un informe fila a fila —
`creado` / `duplicado` / `no_encontrado` / `error` — y **cada fila se confirma
por separado**: un fallo en la fila 40 no deshace las 39 anteriores.

**CRUD completo** sobre las 12 tablas, con las restricciones del esquema
traducidas a respuestas HTTP con sentido: ISBN repetido → 409, referencia
inexistente → 400, ejemplar prestado sin destinatario → 422.

**Cada libro sabe en qué casillero está.** `GET /ejemplares/{id}/localizacion`
sube por las claves foráneas hasta el punto del mueble en el plano de la casa.

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

El `.gpkg` **no está versionado** (`.gitignore` excluye `*.gpkg`): cada quien
tiene sus muebles y sus libros. Créalo con los cinco scripts de `sql/`, en orden:

```bash
sqlite3 sql/gpkg/biblioteca.gpkg < sql/00_gpkg_init.sql             # contenedor GeoPackage 1.3.0
sqlite3 sql/gpkg/biblioteca.gpkg < sql/01_schema.sql                # las 12 tablas de negocio
sqlite3 sql/gpkg/biblioteca.gpkg < sql/02_gpkg_register_layers.sql  # registro de capas
sqlite3 sql/gpkg/biblioteca.gpkg < sql/03_seed_paises.sql           # 250 países, con fronteras
sqlite3 sql/gpkg/biblioteca.gpkg < sql/04_seed_dewey.sql            # 10 clases + 90 divisiones CDD
```

Las semillas usan `INSERT OR IGNORE` y se pueden reejecutar sin efectos; los
tres primeros **fallan con «table already exists» si el archivo ya tiene el
esquema**: son para crear una base nueva, no para actualizar una existente.

Queda una base **vacía de libros y de muebles**: lo único que traen las
semillas son los dos catálogos de referencia a los que apuntan las claves
foráneas —250 países y 100 códigos Dewey—. A partir de ahí, lo primero es
[dar de alta tus muebles](#dónde-está-cada-libro); después ya se pueden
colocar libros en ellos.

`paises` llega **con sus fronteras puestas**: ábrela en QGIS y ya se ve el
mapa. Los polígonos van embebidos en `03_seed_paises.sql` como blobs
GeoPackage, así que no hace falta ninguna herramienta espacial para cargarlos
(ver la [nota 4](#notas-importantes)). Son 250 filas: los 249 códigos ISO
3166-1 más `XK` (Kosovo), que no es ISO pero sí ocupa territorio.

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
  -d '{"isbn":"978-0-14-032872-1","modulo_id":1,"estado_fisico":"bueno"}'
```

Devuelve la ficha completa: libro, autor y editorial recién creados, y el
ejemplar en el casillero 1. Los guiones del ISBN dan igual, y un ISBN mal
tecleado se rechaza por su dígito de control antes de salir a la red.

**`modulo_id` es opcional.** Sin él se cataloga el libro y no se crea ejemplar;
puedes colocarlo más tarde con `PATCH /ejemplares/{id}`.

### Varios de golpe

```bash
curl -X POST localhost:8000/importar/isbns \
  -H 'X-API-Key: elige-una-clave' -H 'Content-Type: application/json' \
  -d '{"isbns":["9788420412146","9780061120084"],"modulo_id":2,"estado_fisico":"bueno"}'
```

### Desde un CSV

`POST /importar/csv`, con cabecera. Hay una plantilla lista para copiar en
[`plantilla_libros.csv`](plantilla_libros.csv):

```bash
curl -X POST localhost:8000/importar/csv \
  -H 'X-API-Key: …' -F 'archivo=@plantilla_libros.csv'
```

**Cada fila se comporta de una de dos maneras, según traiga `isbn` o no.**

Si la fila **tiene ISBN**, el título, el autor, la editorial, el año, las páginas
y el idioma los trae la API de la red; las columnas equivalentes del CSV se
ignoran, así que puedes dejarlas vacías. De la fila solo se leen `isbn`,
`modulo_id`, `estado_fisico` y `notas`.

Si la fila **no tiene ISBN**, no hay nada que consultar y todo sale del CSV. Lo
único obligatorio es `titulo`.

| Columna | Con ISBN | Sin ISBN |
|---|---|---|
| `isbn` | obligatoria; con o sin guiones, se valida el dígito de control | vacía |
| `titulo` | se ignora | **obligatoria** |
| `autor` | se ignora | opcional; varios se separan con `;` |
| `editorial` | se ignora | opcional; se crea si no existe |
| `anio` | se ignora | opcional; se guarda como 1 de enero de ese año |
| `paginas` | se ignora | opcional |
| `idioma` | se ignora | opcional; código de dos letras (`es`, `en`, `fr`) |
| `modulo_id` | opcional | opcional |
| `estado_fisico` | opcional | opcional |
| `notas` | opcional | opcional |

`modulo_id` y `estado_fisico` no describen el libro sino **tu** ejemplar de
él, y por eso valen en ambos casos. Si dejas las dos vacías no se crea ejemplar:
queda la ficha del libro sin copia física asociada. `estado_fisico` solo admite
`nuevo`, `bueno`, `regular` o `dañado`; cualquier otra cosa hace fallar esa fila
—sola, sin arrastrar a las demás.

Detalles del formato: guarda el archivo en **UTF-8** (se acepta BOM), la
cabecera es obligatoria, el orden de las columnas da igual y sobran las que no
uses. Un valor que contenga una coma va **entre comillas dobles**.

### Un libro sin ISBN

`POST /libros` acepta `autor_ids` y `genero_ids` y resuelve las tablas puente
por ti. En `PATCH /libros/{id}`, omitir esas listas deja la relación intacta;
enviarlas la reemplaza entera.

### Dónde está cada libro

La localización se modela en **tres saltos de clave foránea**, y solo el último
tiene geometría:

```
ejemplares.modulo_id  ->  modulos.estanteria_id  ->  estanterias.ubicacion_id  ->  ubicaciones.geom
   la copia                el casillero                  el mueble                  el punto del plano
```

- **`ubicaciones`** es la única capa espacial de dentro de casa: un `POINT` en
  CRS `-1` (plano local) por **mueble**, su huella en el suelo. No un punto por
  balda.
- **`estanterias`** cuelga de ese punto y guarda lo que es del mueble entero:
  medidas totales y `orientacion_grados`, el giro respecto al plano.
- **`modulos`** son los casilleros, en una rejilla `(columna, fila)` que puede
  ser **irregular** —una estantería en escalera con columnas de 1, 2, 3 y 4
  huecos— porque cada hueco es su propia fila. Sus `x_offset_cm` / `z_offset_cm`
  son coordenadas **locales en centímetros** desde el ancla del mueble: la
  geometría 3D se compone al dibujar, fuera de la base.
- **`ejemplares`** apunta al casillero y **nunca** a una ubicación ni a
  coordenadas propias. Un libro está en un hueco concreto, y de ahí se sube.

Dar de alta un mueble son tres llamadas:

```bash
curl -X POST localhost:8000/ubicaciones -H 'X-API-Key: …' \
  -H 'Content-Type: application/json' -d '{"nombre":"escalera","habitacion":"sala"}'

curl -X POST localhost:8000/estanterias -H 'X-API-Key: …' \
  -H 'Content-Type: application/json' \
  -d '{"ubicacion_id":1,"nombre":"escalera","tipo":"biblioteca","orientacion_grados":90}'

curl -X POST localhost:8000/modulos -H 'X-API-Key: …' \
  -H 'Content-Type: application/json' \
  -d '{"estanteria_id":1,"columna":3,"fila":2,"ancho_cm":40,"alto_cm":32}'
```

Y para saber dónde acabó un libro, `GET /ejemplares/{id}/localizacion` recorre
la cadena entera de una vez:

```json
{"ejemplar_id": 3, "titulo": "Cien años de soledad",
 "modulo_id": 2, "columna": 1, "fila": 2,
 "estanteria_id": 3, "estanteria": "central", "tipo": "biblioteca",
 "ubicacion_id": 1, "ubicacion": "central", "habitacion": "sala"}
```

**El perfil de columnas no se guarda, se deriva.** El número de casilleros por
columna ya está en `modulos`, así que la vista `vista_perfil_estanterias` lo
calcula en vez de duplicarlo en una columna que pudiera contradecirlo:

```sql
SELECT estanteria, columnas, modulos, perfil FROM vista_perfil_estanterias;
-- escalera|4|10|1,2,3,4
```

### Salud del ejemplar

`estado_fisico` (`nuevo` / `bueno` / `regular` / `dañado`) es la categoría
general de la copia. Aparte van las cosas que se revisan y se arreglan:
`tiene_hongos`, `requiere_reparacion` y `fecha_revision`.

```bash
curl -X PATCH localhost:8000/ejemplares/3 -H 'X-API-Key: …' \
  -H 'Content-Type: application/json' \
  -d '{"tiene_hongos":true,"requiere_reparacion":true,"fecha_revision":"2026-08-30"}'
```

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
| **Ejemplares** | `GET` `POST` `/ejemplares` · `GET` `PATCH` `DELETE` `/ejemplares/{id}` · `GET /ejemplares/{id}/localizacion` |
| **Mobiliario** | Mismo juego para `/ubicaciones`, `/estanterias`, `/modulos` |
| **Catálogos** | Mismo juego para `/paises`, `/dewey`, `/generos`, `/autores`, `/editoriales` |
| **Estado** | `GET /salud` |

Los listados aceptan `q`, `limit` y `offset`. El filtro `q` mira varias
columnas a la vez, las que uno buscaría de forma natural: a un autor por nombre
o apellidos, a un libro por título, título original o ISBN, a un ejemplar por
sus notas o por a quién está prestado. Además, `/libros` acepta `editorial_id`
e `idioma`, y `/ejemplares` acepta `libro_id`, `modulo_id` y `en_prestamo`.
(`/modulos` no tiene ninguna columna de texto, así que ahí `q` no filtra nada.)

**Las lecturas son abiertas; toda escritura exige la cabecera `X-API-Key`.**

---

## Pruebas

```bash
.venv/bin/python3 -m pytest tests/ -q
```

Construyen la base desde los propios scripts de `sql/` — así validan también que
siguen siendo correctos, que importa porque el `.gpkg` no está versionado y esos
scripts **son** el esquema — y simulan las fuentes externas, por lo que no
dependen de la red.

Son dos archivos, a propósito:

- **`test_esquema.py`** (11) — lo que no se puede comprobar mirando. Una clave
  foránea que deja de aplicarse (`PRAGMA foreign_keys` es por conexión), un
  `CHECK` que ya no salta, un `UNIQUE` que deja pasar dos libros al mismo
  casillero o un GeoPackage que QGIS ya no abre **no dan ningún error el día
  que se rompen**: se descubren meses después, con los datos ya sucios. También
  cubre que un ejemplar se localiza hasta el punto del plano con la cadena de
  `JOIN`s, y que las fronteras de `paises` siguen siendo blobs GeoPackage
  válidos.
- **`test_isbn.py`** (16) — el alta por ISBN y la importación en lote, que es
  la función principal de la API. Simulan Open Library y Google Books, así que
  avisan si un cambio rompe el mapeo de la ficha externa.

Lo que **no** está aquí es deliberado: el CRUD corriente, los filtros de listado
y los mensajes de error se comprueban igual de rápido en `/docs`, y cada cambio
de esquema obliga a reescribirlos. Esas pruebas siguen existiendo en local como
`tests/test_extra.py`, fuera del control de versiones.

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

4. **Geometrías**: `sqlite3` puro no *calcula* un blob GeoPackage a partir de
   WKT o GeoJSON, pero sí inserta uno ya calculado. Por eso
   `03_seed_paises.sql` trae las fronteras embebidas como literales `X'...'`:
   **`paises` es una capa espacial desde el primer `INSERT`**, sin ogr2ogr ni
   QGIS de por medio.

   `ubicaciones.geom` sí queda a NULL —son *tus* muebles, nadie más puede
   saber dónde están—. La API tampoco la escribe: para situarlos en el plano de
   la casa usa QGIS (DB Manager), `ogr2ogr` o Python:
   ```python
   gdf.to_file("biblioteca.gpkg", layer="ubicaciones", driver="GPKG")
   ```
   Todo lo demás de un mueble —medidas, giro, casilleros— se da de alta por la
   API con normalidad; el punto en el plano solo hace falta si quieres verlo
   dibujado.

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

9. **Un ejemplar nunca guarda dónde está, sino en qué hueco**: no hay
   `ejemplares.ubicacion_id` ni coordenadas propias, a propósito. Si las
   hubiera, mover un mueble obligaría a reescribir cada libro que contiene, y
   dos filas podrían acabar diciendo cosas distintas del mismo sitio. Con la
   cadena `modulos -> estanterias -> ubicaciones`, mover el mueble es cambiar
   un punto.

10. **`estanterias.ubicacion_id` es `UNIQUE`**: un punto del plano es la huella
    de un solo mueble. Si algún día hay un mueble en L o dos cuerpos que
    comparten huella, habrá que relajar esa restricción.

11. **La clasificación Dewey de la semilla llega a las divisiones** (10 clases +
   90 divisiones). Las 1000 secciones quedan fuera, pero la notación exacta de
   cada libro se guarda íntegra en `libros.dewey_codigo_completo`: no se pierde
   precisión, `dewey_categoria_id` solo agrupa para poder navegar.
