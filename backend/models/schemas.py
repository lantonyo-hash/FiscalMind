"""
models/schemas.py
Todos los tipos de datos del sistema FiscalMind.
Usar Pydantic para validación automática y documentación OpenAPI.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────

class TipoArchivo(str, Enum):
    compras = "compras"
    ventas  = "ventas"

class EstadoAnalisis(str, Enum):
    ok           = "OK"
    con_errores  = "CON_ERRORES"
    con_alertas  = "CON_ALERTAS"   # Errores leves, F29 igual se calcula


# ── Bloques de error/alerta ────────────────────────────────────────

class Incidencia(BaseModel):
    tipo:    str   # "ERROR_CRITICO" | "ADVERTENCIA"
    codigo:  str   # Código máquina: "IVA_INCORRECTO", "RUT_INVALIDO", ...
    mensaje: str   # Texto amigable para el contador
    fila:    Optional[int | str] = None
    campo:   Optional[str]       = None
    periodo: Optional[str]       = None
    valor:   Optional[str]       = None


# ── Resumen de un período ──────────────────────────────────────────

class ResumenPeriodo(BaseModel):
    periodo:          str
    tipo:             TipoArchivo
    total_registros:  int
    total_neto:       float
    total_iva:        float
    total_importe:    float
    errores:          int
    advertencias:     int


# ── Formulario 29 calculado ────────────────────────────────────────

class Formulario29(BaseModel):
    """
    Campos principales del F29 que se generan a partir de los libros.
    Códigos de línea según el formulario oficial del SII.
    """
    # Ventas (Libro de Ventas)
    ventas_netas:      float = Field(..., description="Base imponible ventas — Línea 503")
    iva_debito:        float = Field(..., description="19% sobre ventas netas — Línea 502")

    # Compras (Libro de Compras)
    compras_netas:     float = Field(..., description="Base imponible compras con derecho a crédito — Línea 520")
    iva_credito:       float = Field(..., description="IVA soportado en compras — Línea 521")

    # Resultado
    iva_determinado:   float = Field(..., description="IVA a pagar = Débito − Crédito — Línea 547/548")
    saldo_a_favor:     float = Field(0,  description="Si crédito > débito, el excedente")

    # Período
    periodo:           str   = Field(..., description="YYYY-MM del período declarado")
    periodos_incluidos: list[str] = Field(default_factory=list)


# ── Respuesta principal del endpoint /f29/calcular ─────────────────

class RespuestaF29(BaseModel):
    estado:          EstadoAnalisis
    formulario_29:   Optional[Formulario29] = None
    resumenes:       list[ResumenPeriodo]   = []
    incidencias:     list[Incidencia]       = []
    texto_copiable:  Optional[str]          = None   # Para copiar/pegar al SII
    analizado_en:    str                    = ""


# ── Solicitud de análisis (multipart viene por Form, esto es el modelo lógico) ─

class SolicitudAnalisis(BaseModel):
    periodos: list[str]       # ["2025-03", "2025-04", ...]
    tipos:    list[TipoArchivo]
