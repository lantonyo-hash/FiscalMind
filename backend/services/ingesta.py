"""
services/ingesta.py
Responsabilidad única: leer y normalizar uno o varios Excel en un DataFrame unificado.

Contrato de salida:
  DataFrame con columnas estándar:
    periodo | tipo | fecha | rut | proveedor | numero_doc |
    tipo_doc | monto_neto | iva | total
"""

import io
import re
import numpy as np
import pandas as pd
from typing import NamedTuple
from models.schemas import TipoArchivo


# ── Mapeo flexible de columnas ────────────────────────────────────
MAPA_COLUMNAS: dict[str, list[str]] = {
    "fecha":       ["fecha", "date", "fecha_doc", "fecha documento", "fec", "fecha_emision"],
    "rut":         ["rut", "rut_proveedor", "rut_cliente", "rutproveedor", "rutcliente", "r.u.t", "rut emisor"],
    "proveedor":   ["proveedor", "cliente", "nombre", "razon_social", "razón social", "emisor", "receptor", "nombre_proveedor"],
    "numero_doc":  ["numero_doc", "n_doc", "ndoc", "folio", "numero", "número", "num_doc", "n° doc", "nro", "folio_doc"],
    "tipo_doc":    ["tipo", "tipo_doc", "tipo_documento", "tdoc", "tipo doc"],
    "monto_neto":  ["neto", "monto_neto", "base_imponible", "base imponible", "valor neto", "afecto"],
    "iva":         ["iva", "monto_iva", "impuesto", "tax", "i.v.a"],
    "total":       ["total", "monto_total", "total_doc", "valor_total", "total documento", "importe"],
}


class ArchivoEntrada(NamedTuple):
    contenido: bytes
    nombre:    str
    tipo:      TipoArchivo
    periodo:   str           # "YYYY-MM"


# ── Helpers ──────────────────────────────────────────────────────

def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas usando el mapa flexible (case-insensitive)."""
    cols_lower = {c.strip().lower(): c for c in df.columns}
    remap = {}
    for estandar, variantes in MAPA_COLUMNAS.items():
        for v in variantes:
            if v.lower() in cols_lower and estandar not in remap.values():
                remap[cols_lower[v.lower()]] = estandar
                break
    return df.rename(columns=remap)


def _a_numero(serie: pd.Series) -> pd.Series:
    """
    Convierte strings con formato chileno ($1.234,56 o 1234567) a float.
    Maneja miles con punto y decimal con coma (estándar chileno).
    """
    def parse(v):
        if pd.isna(v):
            return np.nan
        s = str(v).strip().replace("$", "").replace(" ", "")
        if "," in s and "." in s:         # 1.234,56 → decimal coma
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:                    # 1234,56 → decimal coma sin miles
            s = s.replace(",", ".")
        elif re.search(r'\.\d{3}$', s):   # 1.234 → miles solamente
            s = s.replace(".", "")
        try:
            return float(s)
        except ValueError:
            return np.nan
    return serie.apply(parse)


def _leer_archivo(arch: ArchivoEntrada) -> pd.DataFrame:
    """Lee un archivo Excel o CSV y lo convierte en DataFrame normalizado."""
    buf = io.BytesIO(arch.contenido)
    nombre_lower = arch.nombre.lower()

    if nombre_lower.endswith(".csv"):
        # Intentar separadores comunes
        for sep in [",", ";", "\t"]:
            try:
                df = pd.read_csv(buf, dtype=str, sep=sep)
                if df.shape[1] > 1:
                    break
                buf.seek(0)
            except Exception:
                buf.seek(0)
    else:
        df = pd.read_excel(buf, dtype=str)

    return df


# ── Función principal ─────────────────────────────────────────────

def unificar_archivos(archivos: list[ArchivoEntrada]) -> pd.DataFrame:
    """
    Recibe lista de archivos (compras o ventas por período),
    los lee, normaliza y concatena en un único DataFrame con
    columnas: periodo | tipo | + columnas estándar.

    Raises ValueError si algún archivo no tiene columnas reconocibles.
    """
    frames: list[pd.DataFrame] = []

    for arch in archivos:
        df_raw = _leer_archivo(arch)

        # Eliminar filas completamente vacías
        df_raw = df_raw.dropna(how="all").reset_index(drop=True)

        # Normalizar nombres de columnas
        df = _normalizar_columnas(df_raw)

        # Verificar que al menos existan columnas numéricas clave
        cols_numericas = [c for c in ["monto_neto", "iva", "total"] if c in df.columns]
        if not cols_numericas:
            raise ValueError(
                f"Archivo '{arch.nombre}': no se reconocieron columnas de monto. "
                f"Columnas encontradas: {list(df_raw.columns)}"
            )

        # Convertir columnas numéricas
        for col in cols_numericas:
            df[col] = _a_numero(df[col])

        # Agregar metadatos de período y tipo
        df.insert(0, "periodo", arch.periodo)
        df.insert(1, "tipo", arch.tipo.value)

        frames.append(df)

    if not frames:
        raise ValueError("No se recibieron archivos válidos.")

    # Concatenar y resetear índice
    df_unificado = pd.concat(frames, ignore_index=True, sort=False)
    return df_unificado


def separar_por_tipo(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna (df_compras, df_ventas) desde el DataFrame unificado."""
    compras = df[df["tipo"] == "compras"].copy()
    ventas  = df[df["tipo"] == "ventas"].copy()
    return compras, ventas


def periodos_disponibles(df: pd.DataFrame) -> list[str]:
    """Lista de períodos únicos ordenados cronológicamente."""
    return sorted(df["periodo"].unique().tolist())
