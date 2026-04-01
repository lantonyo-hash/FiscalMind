"""
services/calculador_f29.py
Responsabilidad única: calcular el Formulario 29 a partir del DataFrame validado.

Reglas tributarias Chile:
  - IVA Débito   = suma IVA de ventas afectas
  - IVA Crédito  = suma IVA de compras con derecho a crédito
  - IVA Determinado = Débito − Crédito
  - Si Crédito > Débito → saldo a favor del contribuyente (se arrastra al mes siguiente)
"""

import pandas as pd
from models.schemas import (
    Formulario29,
    ResumenPeriodo,
    TipoArchivo,
)


# ── Helpers ───────────────────────────────────────────────────────

def _sumar(df: pd.DataFrame, col: str) -> float:
    """Suma segura de una columna numérica, ignorando NaN."""
    if col not in df.columns:
        return 0.0
    return float(df[col].sum(skipna=True))


def _resumen_periodo(df_tipo: pd.DataFrame, periodo: str, tipo: TipoArchivo, errores: int, advertencias: int) -> ResumenPeriodo:
    return ResumenPeriodo(
        periodo         = periodo,
        tipo            = tipo,
        total_registros = len(df_tipo),
        total_neto      = _sumar(df_tipo, "monto_neto"),
        total_iva       = _sumar(df_tipo, "iva"),
        total_importe   = _sumar(df_tipo, "total"),
        errores         = errores,
        advertencias    = advertencias,
    )


# ── Función principal ─────────────────────────────────────────────

def calcular_f29(
    df: pd.DataFrame,
    periodo_declarado: str,
    errores_por_periodo: dict[str, int] | None = None,
    advertencias_por_periodo: dict[str, int] | None = None,
) -> tuple[Formulario29, list[ResumenPeriodo]]:
    """
    Calcula el F29 consolidado para el período declarado.

    Si el DataFrame tiene múltiples períodos (ej: enero, febrero, marzo),
    el cálculo agrupa todo como si fuera un solo mes.
    En producción, normalmente se calcula un F29 por mes.

    Retorna:
        (Formulario29, lista de ResumenPeriodo)
    """
    errores_por_periodo     = errores_por_periodo or {}
    advertencias_por_periodo = advertencias_por_periodo or {}

    periodos_en_df = sorted(df["periodo"].unique()) if "periodo" in df.columns else [periodo_declarado]

    # ── Separar compras y ventas ─────────────────────────────────
    df_ventas  = df[df["tipo"] == "ventas"].copy()
    df_compras = df[df["tipo"] == "compras"].copy()

    # ── Calcular totales ─────────────────────────────────────────
    ventas_netas = _sumar(df_ventas, "monto_neto")
    iva_debito   = _sumar(df_ventas, "iva")

    compras_netas = _sumar(df_compras, "monto_neto")
    iva_credito   = _sumar(df_compras, "iva")

    # ── IVA determinado ──────────────────────────────────────────
    iva_determinado = iva_debito - iva_credito
    saldo_a_favor   = max(0.0, -iva_determinado)
    iva_determinado = max(0.0, iva_determinado)

    # ── Formulario 29 ────────────────────────────────────────────
    f29 = Formulario29(
        periodo              = periodo_declarado,
        periodos_incluidos   = periodos_en_df,
        ventas_netas         = round(ventas_netas,  2),
        iva_debito           = round(iva_debito,    2),
        compras_netas        = round(compras_netas, 2),
        iva_credito          = round(iva_credito,   2),
        iva_determinado      = round(iva_determinado, 2),
        saldo_a_favor        = round(saldo_a_favor,   2),
    )

    # ── Resúmenes por período y tipo ─────────────────────────────
    resumenes: list[ResumenPeriodo] = []
    for per in periodos_en_df:
        df_per = df[df["periodo"] == per] if "periodo" in df.columns else df
        errs   = errores_por_periodo.get(per, 0)
        advs   = advertencias_por_periodo.get(per, 0)

        df_v = df_per[df_per["tipo"] == "ventas"]
        df_c = df_per[df_per["tipo"] == "compras"]

        if len(df_v) > 0:
            resumenes.append(_resumen_periodo(df_v, per, TipoArchivo.ventas, errs, advs))
        if len(df_c) > 0:
            resumenes.append(_resumen_periodo(df_c, per, TipoArchivo.compras, errs, advs))

    return f29, resumenes


# ── Texto copiable para el contador ──────────────────────────────

def generar_texto_copiable(f29: Formulario29) -> str:
    """
    Genera un texto estructurado que el contador puede copiar
    y pegar directamente como referencia al completar el F29 en el SII.
    """
    sep = "─" * 50

    def clp(v: float) -> str:
        return f"${v:>14,.0f}".replace(",", ".")

    lineas_incluidas = ", ".join(f29.periodos_incluidos) if f29.periodos_incluidos else f29.periodo

    texto = f"""
╔══════════════════════════════════════════════════╗
║         FORMULARIO 29 — PRE-CÁLCULO              ║
║              FiscalMind · Período {f29.periodo}   ║
╚══════════════════════════════════════════════════╝

  Períodos incluidos: {lineas_incluidas}

{sep}
  VENTAS (Libro de Ventas)
{sep}
  Línea 503 — Ventas netas afectas:   {clp(f29.ventas_netas)}
  Línea 502 — IVA Débito (19%):       {clp(f29.iva_debito)}

{sep}
  COMPRAS (Libro de Compras)
{sep}
  Línea 520 — Compras netas c/crédito:{clp(f29.compras_netas)}
  Línea 521 — IVA Crédito:            {clp(f29.iva_credito)}

{sep}
  RESULTADO
{sep}
  IVA Determinado (Débito − Crédito): {clp(f29.iva_determinado)}
{'  Saldo a favor contribuyente:        ' + clp(f29.saldo_a_favor) if f29.saldo_a_favor > 0 else ''}

  {'⚠  Hay saldo a favor. Arrastra al período siguiente.' if f29.saldo_a_favor > 0 else '✓  IVA a pagar al SII.'}

{sep}
  Generado por FiscalMind — Solo referencial.
  Verifique siempre con su contador tributario.
{sep}
""".strip()

    return texto
