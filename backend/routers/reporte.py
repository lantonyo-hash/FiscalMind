"""
routers/reporte.py
POST /api/reporte/excel — Descarga Excel con resumen del F29 + incidencias.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
import io
from datetime import datetime

from services.ingesta        import ArchivoEntrada, TipoArchivo, unificar_archivos
from services.validador      import validar
from services.calculador_f29 import calcular_f29, generar_texto_copiable

router = APIRouter()


@router.post("/excel", summary="Descargar reporte Excel completo")
async def descargar_excel(
    archivos: list[UploadFile] = File(...),
    periodos: list[str]        = Form(...),
    tipos:    list[str]        = Form(...),
    periodo_declarado: str     = Form(...),
):
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
    errores = [i for i in incidencias if i.tipo == "ERROR_CRITICO"]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        # Hoja 1: F29 si no hay errores
        if not errores:
            f29, resumenes = calcular_f29(df, periodo_declarado)
            resumen_data = {
                "Campo": [
                    "Período declarado",
                    "Ventas netas (L.503)",
                    "IVA Débito (L.502)",
                    "Compras netas (L.520)",
                    "IVA Crédito (L.521)",
                    "IVA Determinado",
                    "Saldo a favor",
                ],
                "Valor ($)": [
                    f29.periodo,
                    f29.ventas_netas,
                    f29.iva_debito,
                    f29.compras_netas,
                    f29.iva_credito,
                    f29.iva_determinado,
                    f29.saldo_a_favor,
                ],
            }
            pd.DataFrame(resumen_data).to_excel(writer, sheet_name="F29 Calculado", index=False)

            texto = generar_texto_copiable(f29)
            df_texto = pd.DataFrame({"Texto copiable": [texto]})
            df_texto.to_excel(writer, sheet_name="Texto Copiable", index=False)
        else:
            pd.DataFrame({"Mensaje": ["No se calculó F29 por errores críticos."]}).to_excel(
                writer, sheet_name="F29 Calculado", index=False
            )

        # Hoja 2: Errores
        if incidencias:
            df_inc = pd.DataFrame([i.model_dump() for i in incidencias])
            df_inc.to_excel(writer, sheet_name="Incidencias", index=False)

        # Hoja 3: Datos unificados
        df.to_excel(writer, sheet_name="Datos", index=False)

    output.seek(0)
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=fiscalmind_{periodo_declarado}_{fecha}.xlsx"},
    )
