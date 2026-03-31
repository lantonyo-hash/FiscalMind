"""
Revisor Contable Inteligente - Backend FastAPI
Valida archivos Excel de contabilidad chilena (IVA, RUTs, facturas)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd
import json
import io
from datetime import datetime
from typing import Optional
from analyzer import ContableAnalyzer

app = FastAPI(
    title="Revisor Contable Inteligente",
    description="Validación automática de libros contables chilenos",
    version="1.0.0"
)

# CORS para desarrollo local (ajustar en producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "app": "Revisor Contable Inteligente v1.0"}


@app.post("/analizar")
async def analizar_archivo(file: UploadFile = File(...)):
    """
    Recibe un Excel/CSV y retorna análisis completo con errores y alertas.
    """
    # Validar extensión
    nombre = file.filename or ""
    if not (nombre.endswith(".xlsx") or nombre.endswith(".csv")):
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos .xlsx o .csv"
        )

    contenido = await file.read()

    try:
        # Leer archivo según tipo
        if nombre.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contenido), dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(contenido), dtype=str)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo leer el archivo: {str(e)}"
        )

    # Ejecutar análisis
    analyzer = ContableAnalyzer(df)
    resultado = analyzer.analizar()

    return resultado


@app.post("/descargar-reporte")
async def descargar_reporte(file: UploadFile = File(...)):
    """
    Genera y descarga reporte Excel con errores encontrados.
    """
    nombre = file.filename or ""
    contenido = await file.read()

    if nombre.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contenido), dtype=str)
    else:
        df = pd.read_excel(io.BytesIO(contenido), dtype=str)

    analyzer = ContableAnalyzer(df)
    resultado = analyzer.analizar()

    # Generar Excel de reporte
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Hoja 1: Resumen
        resumen_data = {
            "Campo": ["Total registros", "Errores críticos", "Advertencias", "Estado general"],
            "Valor": [
                resultado["resumen"]["total_registros"],
                resultado["resumen"]["total_errores"],
                resultado["resumen"]["total_advertencias"],
                resultado["resumen"]["estado"]
            ]
        }
        pd.DataFrame(resumen_data).to_excel(writer, sheet_name="Resumen", index=False)

        # Hoja 2: Errores críticos
        if resultado["errores"]:
            df_errores = pd.DataFrame(resultado["errores"])
            df_errores.to_excel(writer, sheet_name="Errores Críticos", index=False)

        # Hoja 3: Advertencias
        if resultado["advertencias"]:
            df_adv = pd.DataFrame(resultado["advertencias"])
            df_adv.to_excel(writer, sheet_name="Advertencias", index=False)

        # Hoja 4: Datos originales
        df.to_excel(writer, sheet_name="Datos Originales", index=False)

    output.seek(0)
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"reporte_contable_{fecha}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
