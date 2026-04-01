"""
routers/archivos.py
POST /api/archivos/validar — Valida archivos sin calcular F29.
Útil para un paso previo de verificación rápida.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from services.ingesta   import ArchivoEntrada, TipoArchivo, unificar_archivos
from services.validador import validar
from models.schemas     import Incidencia
from datetime           import datetime

router = APIRouter()


@router.post("/validar", summary="Validar archivos sin calcular F29")
async def validar_archivos(
    archivos: list[UploadFile] = File(...),
    periodos: list[str]        = Form(...),
    tipos:    list[str]        = Form(...),
):
    if not (len(archivos) == len(periodos) == len(tipos)):
        raise HTTPException(status_code=422, detail="Cantidad de archivos, períodos y tipos debe coincidir.")

    entradas = []
    for archivo, periodo, tipo in zip(archivos, periodos, tipos):
        contenido = await archivo.read()
        entradas.append(ArchivoEntrada(
            contenido = contenido,
            nombre    = archivo.filename or "archivo",
            tipo      = TipoArchivo(tipo),
            periodo   = periodo,
        ))

    try:
        df = unificar_archivos(entradas)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    incidencias = validar(df)

    return {
        "total_registros": len(df),
        "errores_criticos": sum(1 for i in incidencias if i.tipo == "ERROR_CRITICO"),
        "advertencias":     sum(1 for i in incidencias if i.tipo == "ADVERTENCIA"),
        "incidencias":      [i.model_dump() for i in incidencias],
        "analizado_en":     datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
