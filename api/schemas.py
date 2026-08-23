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
class UbicacionCrear(Base):
    nombre: str = Field(min_length=1)
    habitacion: str | None = None
    mueble: str | None = None
    nivel_balda: str | None = None
    capacidad_estimada: int | None = Field(default=None, ge=0)


class UbicacionEditar(Base):
    nombre: str | None = None
    habitacion: str | None = None
    mueble: str | None = None
    nivel_balda: str | None = None
    capacidad_estimada: int | None = Field(default=None, ge=0)


class Ubicacion(UbicacionCrear):
    id: int


# --------------------------------------------------------------------------- ejemplares
class _EjemplarCampos(Base):
    estado_fisico: EstadoFisico | None = None
    formato: str | None = None
    fecha_adquisicion: date | None = None
    precio_compra: float | None = Field(default=None, ge=0)
    ubicacion_id: int | None = None
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
    ubicacion_id: int | None = None
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
    # Si se indica ubicación o estado, se crea además un ejemplar inicial.
    ubicacion_id: int | None = None
    estado_fisico: EstadoFisico | None = None
    formato: str | None = None
    fecha_adquisicion: date | None = None
    precio_compra: float | None = Field(default=None, ge=0)
    notas: str | None = None


class LibroCreadoDesdeISBN(LibroDetalle):
    fuente: Literal["openlibrary", "googlebooks"]


# --------------------------------------------------------------------------- importación
class LoteISBN(Base):
    isbns: list[str] = Field(min_length=1)
    ubicacion_id: int | None = None
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
