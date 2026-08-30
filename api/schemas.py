"""Modelos Pydantic de entrada y salida.

Reflejan exactamente sql/01_schema.sql. Las columnas `geom` se omiten: quedan
fuera del alcance de esta API (se gestionan con QGIS u ogr2ogr).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EstadoFisico = Literal["nuevo", "bueno", "regular", "dañado"]
NivelDewey = Literal["clase", "division", "seccion"]


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


# --------------------------------------------------------------------------- paises
class PaisCrear(Base):
    codigo_iso: str = Field(min_length=2, max_length=3)
    nombre: str = Field(min_length=1)


class PaisEditar(Base):
    nombre: str | None = None


class Pais(PaisCrear):
    pass


# --------------------------------------------------------------------------- dewey
class DeweyCrear(Base):
    codigo: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    nivel: NivelDewey
    padre_codigo: str | None = None


class DeweyEditar(Base):
    descripcion: str | None = None
    nivel: NivelDewey | None = None
    padre_codigo: str | None = None


class Dewey(DeweyCrear):
    pass


# --------------------------------------------------------------------------- generos
class GeneroCrear(Base):
    nombre: str = Field(min_length=1)
    dewey_relacionado: str | None = None


class GeneroEditar(Base):
    nombre: str | None = None
    dewey_relacionado: str | None = None


class Genero(GeneroCrear):
    id: int


# --------------------------------------------------------------------------- autores
class AutorCrear(Base):
    nombre: str = Field(min_length=1)
    apellidos: str | None = None
    pais_id: str | None = None
    fecha_nacimiento: date | None = None
    fecha_fallecimiento: date | None = None


class AutorEditar(Base):
    nombre: str | None = None
    apellidos: str | None = None
    pais_id: str | None = None
    fecha_nacimiento: date | None = None
    fecha_fallecimiento: date | None = None


class Autor(AutorCrear):
    id: int


# --------------------------------------------------------------------------- editoriales
class EditorialCrear(Base):
    nombre: str = Field(min_length=1)
    pais_id: str | None = None
    ciudad_publicacion: str | None = None


class EditorialEditar(Base):
    nombre: str | None = None
    pais_id: str | None = None
    ciudad_publicacion: str | None = None


class Editorial(EditorialCrear):
    id: int


# --------------------------------------------------------------------------- ubicaciones
# Un punto del plano de la casa: la huella de un mueble, no la de una balda.
class UbicacionCrear(Base):
    nombre: str = Field(min_length=1)
    habitacion: str | None = None


class UbicacionEditar(Base):
    nombre: str | None = None
    habitacion: str | None = None


class Ubicacion(UbicacionCrear):
    id: int


# --------------------------------------------------------------------------- estanterias
class EstanteriaCrear(Base):
    ubicacion_id: int
    nombre: str = Field(min_length=1)
    tipo: str | None = None
    ancho_total_cm: float | None = Field(default=None, gt=0)
    alto_total_cm: float | None = Field(default=None, gt=0)
    profundidad_cm: float | None = Field(default=None, gt=0)
    orientacion_grados: float = Field(default=0, ge=0, lt=360)


class EstanteriaEditar(Base):
    ubicacion_id: int | None = None
    nombre: str | None = None
    tipo: str | None = None
    ancho_total_cm: float | None = Field(default=None, gt=0)
    alto_total_cm: float | None = Field(default=None, gt=0)
    profundidad_cm: float | None = Field(default=None, gt=0)
    orientacion_grados: float | None = Field(default=None, ge=0, lt=360)


class Estanteria(EstanteriaCrear):
    id: int


# --------------------------------------------------------------------------- modulos
# Un casillero. `x_offset_cm`/`z_offset_cm` son coordenadas LOCALES en cm desde
# el ancla del mueble; nunca coordenadas del plano de la casa.
class ModuloCrear(Base):
    estanteria_id: int
    columna: int = Field(ge=1)
    fila: int = Field(ge=1)
    x_offset_cm: float | None = None
    z_offset_cm: float | None = None
    ancho_cm: float | None = Field(default=None, gt=0)
    alto_cm: float | None = Field(default=None, gt=0)
    profundidad_cm: float | None = Field(default=None, gt=0)
    capacidad_estimada: int | None = Field(default=None, ge=0)


class ModuloEditar(Base):
    estanteria_id: int | None = None
    columna: int | None = Field(default=None, ge=1)
    fila: int | None = Field(default=None, ge=1)
    x_offset_cm: float | None = None
    z_offset_cm: float | None = None
    ancho_cm: float | None = Field(default=None, gt=0)
    alto_cm: float | None = Field(default=None, gt=0)
    profundidad_cm: float | None = Field(default=None, gt=0)
    capacidad_estimada: int | None = Field(default=None, ge=0)


class Modulo(ModuloCrear):
    id: int


class Localizacion(Base):
    """Dónde está un ejemplar, resuelto por la cadena de claves foráneas."""

    ejemplar_id: int
    titulo: str
    modulo_id: int
    columna: int
    fila: int
    estanteria_id: int
    estanteria: str
    tipo: str | None = None
    ubicacion_id: int
    ubicacion: str
    habitacion: str | None = None


# --------------------------------------------------------------------------- ejemplares
class _EjemplarCampos(Base):
    estado_fisico: EstadoFisico | None = None
    formato: str | None = None
    fecha_adquisicion: date | None = None
    precio_compra: float | None = Field(default=None, ge=0)
    # El sitio de una copia es un casillero, no un punto del plano: la ubicación
    # se deduce subiendo por modulos -> estanterias -> ubicaciones.
    modulo_id: int | None = None
    tiene_hongos: bool = False
    requiere_reparacion: bool = False
    fecha_revision: date | None = None
    en_prestamo: bool = False
    prestado_a: str | None = None
    notas: str | None = None

    @model_validator(mode="after")
    def _prestamo_coherente(self):
        # Réplica del CHECK del esquema, para dar un error legible antes de
        # llegar a SQLite.
        if self.en_prestamo and not self.prestado_a:
            raise ValueError("Un ejemplar en préstamo necesita 'prestado_a'.")
        return self


class EjemplarCrear(_EjemplarCampos):
    libro_id: int


class EjemplarEditar(Base):
    estado_fisico: EstadoFisico | None = None
    formato: str | None = None
    fecha_adquisicion: date | None = None
    precio_compra: float | None = Field(default=None, ge=0)
    modulo_id: int | None = None
    tiene_hongos: bool | None = None
    requiere_reparacion: bool | None = None
    fecha_revision: date | None = None
    en_prestamo: bool | None = None
    prestado_a: str | None = None
    notas: str | None = None


class Ejemplar(EjemplarCrear):
    id: int


# --------------------------------------------------------------------------- libros
class _LibroCampos(Base):
    titulo: str = Field(min_length=1)
    titulo_original: str | None = None
    isbn: str | None = None
    idioma: str | None = None
    dewey_codigo_completo: str | None = None
    dewey_categoria_id: str | None = None
    fecha_publicacion: date | None = None
    fecha_escritura_original: date | None = None
    numero_paginas: int | None = Field(default=None, ge=1)
    sinopsis: str | None = None
    portada_path: str | None = None
    editorial_id: int | None = None


class LibroCrear(_LibroCampos):
    autor_ids: list[int] = Field(default_factory=list)
    genero_ids: list[int] = Field(default_factory=list)


class LibroEditar(Base):
    titulo: str | None = None
    titulo_original: str | None = None
    isbn: str | None = None
    idioma: str | None = None
    dewey_codigo_completo: str | None = None
    dewey_categoria_id: str | None = None
    fecha_publicacion: date | None = None
    fecha_escritura_original: date | None = None
    numero_paginas: int | None = Field(default=None, ge=1)
    sinopsis: str | None = None
    portada_path: str | None = None
    editorial_id: int | None = None
    # None = no tocar la relación; lista = reemplazarla por completo.
    autor_ids: list[int] | None = None
    genero_ids: list[int] | None = None


class Libro(_LibroCampos):
    id: int


class LibroDetalle(Libro):
    autores: list[Autor] = Field(default_factory=list)
    generos: list[Genero] = Field(default_factory=list)
    editorial: Editorial | None = None
    ejemplares: list[Ejemplar] = Field(default_factory=list)


# --------------------------------------------------------------------------- ISBN
class FichaISBN(Base):
    """Ficha normalizada devuelta por las fuentes externas, sin persistir."""

    fuente: Literal["openlibrary", "googlebooks"]
    isbn: str
    titulo: str
    titulo_original: str | None = None
    idioma: str | None = None
    fecha_publicacion: date | None = None
    numero_paginas: int | None = None
    sinopsis: str | None = None
    portada_path: str | None = None
    dewey_codigo_completo: str | None = None
    editorial: str | None = None
    autores: list[str] = Field(default_factory=list)


class DesdeISBN(Base):
    isbn: str
    # Todo lo demás es opcional y describe TU copia, no el libro: si se indica
    # algo de esto se crea además un ejemplar inicial, colocado en `modulo_id`
    # si se da uno.
    modulo_id: int | None = None
    estado_fisico: EstadoFisico | None = None
    formato: str | None = None
    fecha_adquisicion: date | None = None
    precio_compra: float | None = Field(default=None, ge=0)
    tiene_hongos: bool = False
    requiere_reparacion: bool = False
    notas: str | None = None


class LibroCreadoDesdeISBN(LibroDetalle):
    fuente: Literal["openlibrary", "googlebooks"]


# --------------------------------------------------------------------------- importación
class LoteISBN(Base):
    isbns: list[str] = Field(min_length=1)
    modulo_id: int | None = None
    estado_fisico: EstadoFisico | None = None


class ResultadoFila(Base):
    fila: int
    isbn: str | None = None
    titulo: str | None = None
    estado: Literal["creado", "duplicado", "no_encontrado", "error"]
    libro_id: int | None = None
    detalle: str | None = None


class InformeImportacion(Base):
    total: int
    creados: int
    duplicados: int
    no_encontrados: int
    errores: int
    filas: list[ResultadoFila]
