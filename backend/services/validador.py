"""
services/validador.py
Responsabilidad única: detectar errores críticos y advertencias en el DataFrame unificado.

Retorna lista de Incidencia sin modificar el DataFrame original.
"""

import numpy as np
import pandas as pd
import re
from models.schemas import Incidencia


IVA_TASA       = 0.19
IVA_TOLERANCIA = 1   # pesos de tolerancia por redondeo


# ── Validación de RUT chileno (módulo 11) ─────────────────────────

def _limpiar_rut(rut: str) -> str:
    return str(rut).replace(".", "").replace("-", "").replace(" ", "").upper().strip()


def _rut_valido(rut_raw: str) -> bool:
    rut = _limpiar_rut(rut_raw)
    if len(rut) < 2:
        return False
    cuerpo, dv = rut[:-1], rut[-1]
    if not cuerpo.isdigit():
        return False
    suma, mult = 0, 2
    for c in reversed(cuerpo):
        suma += int(c) * mult
        mult = mult + 1 if mult < 7 else 2
    resto   = 11 - (suma % 11)
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return dv == esperado


def _fmt_clp(v: float) -> str:
    return f"${v:,.0f}".replace(",", ".")


# ── Validaciones individuales ─────────────────────────────────────

def _validar_campos_obligatorios(df: pd.DataFrame) -> list[Incidencia]:
    inc: list[Incidencia] = []
    campos = ["rut", "monto_neto", "iva", "total"]
    for campo in campos:
        if campo not in df.columns:
            continue
        for idx, val in df[campo].items():
            if pd.isna(val) or str(val).strip() == "":
                inc.append(Incidencia(
                    tipo    = "ERROR_CRITICO",
                    codigo  = "CAMPO_VACIO",
                    mensaje = f"Campo obligatorio vacío: '{campo.replace('_', ' ').title()}'",
                    fila    = int(idx) + 2,
                    campo   = campo,
                    periodo = df.at[idx, "periodo"] if "periodo" in df.columns else None,
                ))
    return inc


def _validar_ruts(df: pd.DataFrame) -> list[Incidencia]:
    inc: list[Incidencia] = []
    if "rut" not in df.columns:
        return inc
    for idx, rut in df["rut"].items():
        if pd.isna(rut) or str(rut).strip() == "":
            continue
        if not _rut_valido(str(rut)):
            inc.append(Incidencia(
                tipo    = "ERROR_CRITICO",
                codigo  = "RUT_INVALIDO",
                mensaje = f"RUT inválido (dígito verificador incorrecto): {rut}",
                fila    = int(idx) + 2,
                campo   = "rut",
                periodo = df.at[idx, "periodo"] if "periodo" in df.columns else None,
                valor   = str(rut),
            ))
    return inc


def _validar_iva(df: pd.DataFrame) -> list[Incidencia]:
    inc: list[Incidencia] = []
    if not {"monto_neto", "iva"}.issubset(df.columns):
        return inc
    for idx, row in df.iterrows():
        neto = row.get("monto_neto")
        iva  = row.get("iva")
        if pd.isna(neto) or pd.isna(iva):
            continue
        esperado = round(float(neto) * IVA_TASA)
        if abs(float(iva) - esperado) > IVA_TOLERANCIA:
            inc.append(Incidencia(
                tipo    = "ERROR_CRITICO",
                codigo  = "IVA_INCORRECTO",
                mensaje = (
                    f"IVA inconsistente: declarado {_fmt_clp(float(iva))} "
                    f"pero debería ser {_fmt_clp(esperado)} "
                    f"(19% de {_fmt_clp(float(neto))})"
                ),
                fila    = int(idx) + 2,
                campo   = "iva",
                periodo = row.get("periodo"),
                valor   = str(iva),
            ))
    return inc


def _validar_totales(df: pd.DataFrame) -> list[Incidencia]:
    inc: list[Incidencia] = []
    if not {"monto_neto", "iva", "total"}.issubset(df.columns):
        return inc
    for idx, row in df.iterrows():
        neto  = row.get("monto_neto")
        iva   = row.get("iva")
        total = row.get("total")
        if any(pd.isna(v) for v in [neto, iva, total]):
            continue
        esperado = float(neto) + float(iva)
        if abs(float(total) - esperado) > IVA_TOLERANCIA:
            inc.append(Incidencia(
                tipo    = "ERROR_CRITICO",
                codigo  = "TOTAL_INCONSISTENTE",
                mensaje = (
                    f"Total no cuadra: Neto {_fmt_clp(float(neto))} + IVA {_fmt_clp(float(iva))} "
                    f"= {_fmt_clp(esperado)} ≠ Total declarado {_fmt_clp(float(total))}"
                ),
                fila    = int(idx) + 2,
                campo   = "total",
                periodo = row.get("periodo"),
                valor   = str(total),
            ))
    return inc


def _validar_duplicados(df: pd.DataFrame) -> list[Incidencia]:
    """Detecta misma combinación rut + numero_doc dentro del mismo tipo y período."""
    inc: list[Incidencia] = []
    if not {"rut", "numero_doc"}.issubset(df.columns):
        return inc

    # Clave: periodo + tipo + rut + numero_doc
    claves = ["periodo", "tipo", "rut", "numero_doc"]
    claves_existentes = [c for c in claves if c in df.columns]
    clave_serie = df[claves_existentes].astype(str).agg("||".join, axis=1)
    dups = clave_serie[clave_serie.duplicated(keep=False)]

    vistos: set[str] = set()
    for idx in dups.index:
        k = dups[idx]
        if k in vistos:
            continue
        vistos.add(k)
        filas = [str(i + 2) for i in dups[dups == k].index.tolist()]
        row   = df.loc[idx]
        inc.append(Incidencia(
            tipo    = "ERROR_CRITICO",
            codigo  = "FACTURA_DUPLICADA",
            mensaje = (
                f"Factura duplicada: RUT {row.get('rut', '?')} — "
                f"Doc N° {row.get('numero_doc', '?')} "
                f"aparece en filas {', '.join(filas)}"
            ),
            fila    = f"Filas {', '.join(filas)}",
            campo   = "numero_doc",
            periodo = row.get("periodo"),
            valor   = str(row.get("numero_doc", "")),
        ))
    return inc


# ── Validaciones inteligentes (anomalías) ────────────────────────

def _detectar_proveedores_nuevos(df: pd.DataFrame) -> list[Incidencia]:
    """
    Si hay múltiples períodos, alerta sobre proveedores que aparecen
    en el último período pero no en períodos anteriores.
    Si solo hay un período, alerta si aparece una sola vez.
    """
    inc: list[Incidencia] = []
    if "proveedor" not in df.columns:
        return inc
    periodos = sorted(df["periodo"].unique()) if "periodo" in df.columns else []

    if len(periodos) >= 2:
        ultimo     = periodos[-1]
        anteriores = df[df["periodo"] != ultimo]["proveedor"].dropna().unique()
        nuevos     = df[df["periodo"] == ultimo]["proveedor"].dropna().unique()
        for p in nuevos:
            if p not in anteriores and str(p).strip():
                fila_idx = df[(df["periodo"] == ultimo) & (df["proveedor"] == p)].index[0]
                inc.append(Incidencia(
                    tipo    = "ADVERTENCIA",
                    codigo  = "PROVEEDOR_NUEVO",
                    mensaje = f"Proveedor/cliente nuevo en {ultimo}: '{p}' (no aparece en períodos anteriores)",
                    fila    = int(fila_idx) + 2,
                    campo   = "proveedor",
                    periodo = ultimo,
                    valor   = str(p),
                ))
    else:
        conteo = df["proveedor"].value_counts()
        for prov, cnt in conteo.items():
            if cnt == 1 and str(prov).strip():
                fila_idx = df[df["proveedor"] == prov].index[0]
                inc.append(Incidencia(
                    tipo    = "ADVERTENCIA",
                    codigo  = "PROVEEDOR_NUEVO",
                    mensaje = f"Proveedor/cliente nuevo: '{prov}' (aparece una sola vez en el archivo)",
                    fila    = int(fila_idx) + 2,
                    campo   = "proveedor",
                    periodo = df.at[fila_idx, "periodo"] if "periodo" in df.columns else None,
                    valor   = str(prov),
                ))
    return inc


def _detectar_montos_atipicos(df: pd.DataFrame) -> list[Incidencia]:
    """Z-score > 3 sobre los totales del libro completo."""
    inc: list[Incidencia] = []
    if "total" not in df.columns:
        return inc
    totales = df["total"].dropna()
    if len(totales) < 5:
        return inc
    media = totales.mean()
    std   = totales.std()
    if std == 0:
        return inc
    for idx, v in totales.items():
        z = abs((v - media) / std)
        if z > 3:
            inc.append(Incidencia(
                tipo    = "ADVERTENCIA",
                codigo  = "MONTO_ATIPICO",
                mensaje = (
                    f"Monto atípico: {_fmt_clp(float(v))} "
                    f"está {z:.1f} desv. estándar del promedio ({_fmt_clp(float(media))})"
                ),
                fila    = int(idx) + 2,
                campo   = "total",
                periodo = df.at[idx, "periodo"] if "periodo" in df.columns else None,
                valor   = str(v),
            ))
    return inc


def _detectar_variacion_interpériodica(df: pd.DataFrame) -> list[Incidencia]:
    """
    Compara el total neto de cada período vs el anterior.
    Alerta si la variación supera el 100% o cae más del 60%.
    Solo aplica cuando hay ≥ 2 períodos.
    """
    inc: list[Incidencia] = []
    if "periodo" not in df.columns or "monto_neto" not in df.columns:
        return inc
    por_periodo = (
        df.groupby(["periodo", "tipo"])["monto_neto"]
        .sum()
        .reset_index()
        .sort_values("periodo")
    )
    for tipo in por_periodo["tipo"].unique():
        sub = por_periodo[por_periodo["tipo"] == tipo].reset_index(drop=True)
        for i in range(1, len(sub)):
            prev  = sub.at[i - 1, "monto_neto"]
            curr  = sub.at[i,     "monto_neto"]
            per   = sub.at[i,     "periodo"]
            per_p = sub.at[i - 1, "periodo"]
            if prev == 0:
                continue
            ratio = (curr - prev) / prev
            if ratio > 1.0 or ratio < -0.6:
                direccion = "aumentó" if ratio > 0 else "cayó"
                inc.append(Incidencia(
                    tipo    = "ADVERTENCIA",
                    codigo  = "VARIACION_INTERPERIODICA",
                    mensaje = (
                        f"El total neto de {tipo} {direccion} un {abs(ratio):.0%} "
                        f"entre {per_p} ({_fmt_clp(float(prev))}) "
                        f"y {per} ({_fmt_clp(float(curr))})"
                    ),
                    periodo = per,
                    campo   = "monto_neto",
                ))
    return inc


def _detectar_cambios_bruscos_consecutivos(df: pd.DataFrame) -> list[Incidencia]:
    """Ratio > 5x entre documentos consecutivos dentro del mismo período."""
    inc: list[Incidencia] = []
    if "total" not in df.columns:
        return inc
    totales = df["total"].dropna()
    for j in range(1, len(totales)):
        prev = totales.iloc[j - 1]
        curr = totales.iloc[j]
        if prev == 0:
            continue
        r = abs(curr / prev)
        if r > 5 or r < 0.2:
            idx = totales.index[j]
            inc.append(Incidencia(
                tipo    = "ADVERTENCIA",
                codigo  = "CAMBIO_BRUSCO",
                mensaje = (
                    f"Cambio brusco entre documentos consecutivos: "
                    f"{_fmt_clp(float(prev))} → {_fmt_clp(float(curr))} (×{r:.1f}). "
                    f"Verifique posible error tipográfico."
                ),
                fila    = int(idx) + 2,
                campo   = "total",
                periodo = df.at[idx, "periodo"] if "periodo" in df.columns else None,
                valor   = str(curr),
            ))
    return inc


# ── Función principal exportada ───────────────────────────────────

def validar(df: pd.DataFrame) -> list[Incidencia]:
    """
    Ejecuta todas las validaciones sobre el DataFrame unificado.
    Retorna lista de Incidencia ordenada: errores críticos primero.
    """
    inc: list[Incidencia] = []

    inc += _validar_campos_obligatorios(df)
    inc += _validar_ruts(df)
    inc += _validar_iva(df)
    inc += _validar_totales(df)
    inc += _validar_duplicados(df)
    inc += _detectar_proveedores_nuevos(df)
    inc += _detectar_montos_atipicos(df)
    inc += _detectar_variacion_interpériodica(df)
    inc += _detectar_cambios_bruscos_consecutivos(df)

    # Errores críticos primero
    inc.sort(key=lambda x: 0 if x.tipo == "ERROR_CRITICO" else 1)
    return inc
