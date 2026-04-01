"""
routers/f29.py
POST /api/f29/calcular — Endpoint principal de FiscalMind.

Recibe múltiples archivos con metadatos de período y tipo,
ejecuta el pipeline completo y devuelve el F29 + incidencias.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from datetime import datetime
import re

from services.ingesta        import ArchivoEntrada, TipoArchivo, unificar_archivos
from services.validador      import validar
from services.calculador_f29 import calcular_f29, generar_texto_copiable
from models.schemas          import RespuestaF29, EstadoAnalisis, Incidencia

router = APIRouter()


def _validar_formato_periodo(periodo: str) -> bool:
    return bool(re.match(r"^\d{4}-(0[1-9]|1[0-2])$", periodo))


@router.post(
    "/calcular",
    response_model   = RespuestaF29,
    summary          = "Calcular Formulario 29",
    description      = (
        "Recibe 1 a 6 archivos Excel (compras/ventas por período). "
        "Valida, detecta anomalías y calcula el F29 si no hay errores críticos."
    ),
)
async def calcular(
    # Archivos
    archivos: list[UploadFile] = File(..., description="Excel o CSV de compras/ventas"),

    # Metadatos paralelos a los archivos (mismo orden)
    periodos: list[str] = Form(..., description="Período de cada archivo: YYYY-MM"),
    tipos:    list[str] = Form(..., description="Tipo: 'compras' o 'ventas'"),

    # Período de declaración (por defecto = período más reciente)
    periodo_declarado: Optional[str] = Form(None),
):
    # ── Validar metadatos de entrada ────────────────────────────
    if not (len(archivos) == len(periodos) == len(tipos)):
        raise HTTPException(
            status_code=422,
            detail=(
                f"La cantidad de archivos ({len(archivos)}), períodos ({len(periodos)}) "
                f"y tipos ({len(tipos)}) debe ser igual."
            ),
        )

    if len(archivos) > 6:
        raise HTTPException(status_code=422, detail="Máximo 6 archivos por solicitud.")

    for p in periodos:
        if not _validar_formato_periodo(p):
            raise HTTPException(status_code=422, detail=f"Período inválido: '{p}'. Use formato YYYY-MM.")

    tipos_validos = {t.value for t in TipoArchivo}
    for t in tipos:
        if t not in tipos_validos:
            raise HTTPException(status_code=422, detail=f"Tipo inválido: '{t}'. Use 'compras' o 'ventas'.")

    # ── Leer contenido de los archivos ─────────────────────────
    entradas: list[ArchivoEntrada] = []
    for archivo, periodo, tipo in zip(archivos, periodos, tipos):
        contenido = await archivo.read()
        entradas.append(ArchivoEntrada(
            contenido = contenido,
            nombre    = archivo.filename or "archivo",
            tipo      = TipoArchivo(tipo),
            periodo   = periodo,
        ))

    # ── Pipeline de procesamiento ────────────────────────────────
    try:
        df = unificar_archivos(entradas)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Determinar período de declaración
    periodos_disponibles = sorted(df["periodo"].unique().tolist())
    periodo_decl = periodo_declarado or periodos_disponibles[-1]

    # Validar
    incidencias = validar(df)

    errores      = [i for i in incidencias if i.tipo == "ERROR_CRITICO"]
    advertencias = [i for i in incidencias if i.tipo == "ADVERTENCIA"]

    # Contadores por período para el resumen
    errores_por_per: dict[str, int] = {}
    for e in errores:
        if e.periodo:
            errores_por_per[e.periodo] = errores_por_per.get(e.periodo, 0) + 1

    advs_por_per: dict[str, int] = {}
    for a in advertencias:
        if a.periodo:
            advs_por_per[a.periodo] = advs_por_per.get(a.periodo, 0) + 1

    # Estado
    if errores:
        estado = EstadoAnalisis.con_errores
    elif advertencias:
        estado = EstadoAnalisis.con_alertas
    else:
        estado = EstadoAnalisis.ok

    # Calcular F29 solo si no hay errores críticos
    f29_resultado    = None
    resumenes        = []
    texto_copiable   = None

    if not errores:
        f29_resultado, resumenes = calcular_f29(
            df                    = df,
            periodo_declarado     = periodo_decl,
            errores_por_periodo   = errores_por_per,
            advertencias_por_periodo = advs_por_per,
        )
        texto_copiable = generar_texto_copiable(f29_resultado)

    return RespuestaF29(
        estado         = estado,
        formulario_29  = f29_resultado,
        resumenes      = resumenes,
        incidencias    = incidencias,
        texto_copiable = texto_copiable,
        analizado_en   = datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    )
