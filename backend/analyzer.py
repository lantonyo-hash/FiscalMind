"""
ContableAnalyzer - Motor de validación contable chileno
Implementa todas las reglas tributarias y detección de anomalías
"""

import pandas as pd
import numpy as np
import re
from typing import Any


# ─────────────────────────────────────────────
# UTILIDADES RUT CHILENO
# ─────────────────────────────────────────────

def limpiar_rut(rut_raw: str) -> str:
    """Elimina puntos, guiones y espacios del RUT."""
    if not rut_raw or pd.isna(rut_raw):
        return ""
    return str(rut_raw).replace(".", "").replace("-", "").replace(" ", "").upper().strip()


def validar_rut(rut_raw: str) -> bool:
    """
    Valida RUT chileno usando algoritmo módulo 11.
    Formato esperado: 12345678K o 123456789 (sin puntos ni guión)
    """
    rut = limpiar_rut(rut_raw)
    if len(rut) < 2:
        return False

    cuerpo = rut[:-1]
    dv = rut[-1]

    if not cuerpo.isdigit():
        return False

    # Cálculo módulo 11
    suma = 0
    multiplo = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplo
        multiplo = multiplo + 1 if multiplo < 7 else 2

    resto = 11 - (suma % 11)
    if resto == 11:
        dv_calculado = "0"
    elif resto == 10:
        dv_calculado = "K"
    else:
        dv_calculado = str(resto)

    return dv == dv_calculado


# ─────────────────────────────────────────────
# NORMALIZADOR DE COLUMNAS
# ─────────────────────────────────────────────

# Mapeo flexible: variantes de nombres → nombre estándar
COLUMNAS_MAPA = {
    "fecha": ["fecha", "date", "fecha_doc", "fecha documento", "fec"],
    "rut": ["rut", "rut_proveedor", "rut_cliente", "rutproveedor", "rutcliente", "r.u.t"],
    "proveedor": ["proveedor", "cliente", "nombre", "razon_social", "razón social", "emisor", "receptor"],
    "numero_doc": ["numero_doc", "n_doc", "ndoc", "folio", "numero", "número", "num_doc", "n° doc", "nro"],
    "monto_neto": ["neto", "monto_neto", "montonto", "base_imponible", "base imponible", "valor neto"],
    "iva": ["iva", "monto_iva", "impuesto", "tax"],
    "total": ["total", "monto_total", "total_doc", "valor_total", "total documento"],
    "tipo_doc": ["tipo", "tipo_doc", "tipo_documento", "tdoc"],
}


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Renombra columnas del DataFrame para usar nombres estándar.
    Caso-insensitivo y tolerante a variaciones.
    """
    col_map = {}
    cols_lower = {c.lower().strip(): c for c in df.columns}

    for nombre_estandar, variantes in COLUMNAS_MAPA.items():
        for variante in variantes:
            if variante.lower() in cols_lower:
                col_original = cols_lower[variante.lower()]
                col_map[col_original] = nombre_estandar
                break

    return df.rename(columns=col_map)


def a_numero(valor: Any) -> float:
    """Convierte string con formato chileno ($1.234,56) a float."""
    if pd.isna(valor):
        return np.nan
    s = str(valor).strip().replace("$", "").replace(" ", "")
    # Formato chileno: punto=miles, coma=decimal
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


# ─────────────────────────────────────────────
# ANALIZADOR PRINCIPAL
# ─────────────────────────────────────────────

class ContableAnalyzer:
    """
    Motor principal de validación contable chilena.
    Recibe un DataFrame y retorna errores críticos + advertencias.
    """

    IVA_TASA = 0.19  # Tasa IVA Chile
    IVA_TOLERANCIA = 1  # Tolerancia en pesos por redondeo

    def __init__(self, df: pd.DataFrame):
        self.df_original = df.copy()
        self.df = normalizar_columnas(df.copy())
        self.errores: list[dict] = []
        self.advertencias: list[dict] = []
        self.columnas_disponibles = list(self.df.columns)

    # ── helpers ──────────────────────────────

    def _tiene_col(self, *cols) -> bool:
        return all(c in self.df.columns for c in cols)

    def _agregar_error(self, fila: int | str, campo: str, mensaje: str, valor: Any = None):
        self.errores.append({
            "fila": fila,
            "campo": campo,
            "tipo": "ERROR CRÍTICO",
            "mensaje": mensaje,
            "valor": str(valor) if valor is not None else ""
        })

    def _agregar_advertencia(self, fila: int | str, campo: str, mensaje: str, valor: Any = None):
        self.advertencias.append({
            "fila": fila,
            "campo": campo,
            "tipo": "ADVERTENCIA",
            "mensaje": mensaje,
            "valor": str(valor) if valor is not None else ""
        })

    # ── validaciones básicas ─────────────────

    def _validar_campos_requeridos(self):
        """Detecta celdas vacías en columnas críticas."""
        campos_criticos = ["rut", "monto_neto", "iva", "total"]
        for campo in campos_criticos:
            if campo not in self.df.columns:
                continue
            for i, valor in self.df[campo].items():
                if pd.isna(valor) or str(valor).strip() == "":
                    self._agregar_error(
                        i + 2, campo,
                        f"Campo obligatorio vacío: {campo.replace('_', ' ').title()}",
                        valor
                    )

    def _validar_ruts(self):
        """Valida formato y dígito verificador de todos los RUTs."""
        if "rut" not in self.df.columns:
            return
        for i, rut in self.df["rut"].items():
            if pd.isna(rut) or str(rut).strip() == "":
                continue  # Ya detectado en campos requeridos
            if not validar_rut(str(rut)):
                self._agregar_error(
                    i + 2, "rut",
                    f"RUT inválido (dígito verificador incorrecto)",
                    rut
                )

    def _validar_iva(self):
        """Verifica que IVA = Neto × 19% (con tolerancia de $1 por redondeo)."""
        if not self._tiene_col("monto_neto", "iva"):
            return
        for i, row in self.df.iterrows():
            neto = a_numero(row.get("monto_neto"))
            iva = a_numero(row.get("iva"))
            if np.isnan(neto) or np.isnan(iva):
                continue
            iva_esperado = round(neto * self.IVA_TASA)
            if abs(iva - iva_esperado) > self.IVA_TOLERANCIA:
                self._agregar_error(
                    i + 2, "iva",
                    f"IVA inconsistente: declarado ${iva:,.0f} pero debería ser ${iva_esperado:,.0f} (19% de ${neto:,.0f})",
                    iva
                )

    def _validar_totales(self):
        """Verifica que Neto + IVA = Total."""
        if not self._tiene_col("monto_neto", "iva", "total"):
            return
        for i, row in self.df.iterrows():
            neto = a_numero(row.get("monto_neto"))
            iva = a_numero(row.get("iva"))
            total = a_numero(row.get("total"))
            if any(np.isnan(v) for v in [neto, iva, total]):
                continue
            total_esperado = neto + iva
            if abs(total - total_esperado) > self.IVA_TOLERANCIA:
                self._agregar_error(
                    i + 2, "total",
                    f"Total inconsistente: Neto ${neto:,.0f} + IVA ${iva:,.0f} = ${total_esperado:,.0f} ≠ Total declarado ${total:,.0f}",
                    total
                )

    def _validar_duplicados(self):
        """Detecta facturas duplicadas por RUT + número de documento."""
        if not self._tiene_col("rut", "numero_doc"):
            return
        clave = self.df[["rut", "numero_doc"]].astype(str).agg("-".join, axis=1)
        duplicados = clave[clave.duplicated(keep=False)]
        filas_reportadas = set()
        for i in duplicados.index:
            key = duplicados[i]
            if key not in filas_reportadas:
                filas_reportadas.add(key)
                rut = self.df.at[i, "rut"]
                ndoc = self.df.at[i, "numero_doc"]
                filas_dup = [str(x + 2) for x in duplicados[duplicados == key].index.tolist()]
                self._agregar_error(
                    f"Filas {', '.join(filas_dup)}", "numero_doc",
                    f"Factura duplicada: RUT {rut} - Doc N° {ndoc} aparece {len(filas_dup)} veces",
                    ndoc
                )

    def _validar_fechas(self):
        """Verifica que las fechas sean válidas y no futuras."""
        if "fecha" not in self.df.columns:
            return
        hoy = pd.Timestamp.now()
        for i, fecha_raw in self.df["fecha"].items():
            if pd.isna(fecha_raw) or str(fecha_raw).strip() == "":
                self._agregar_advertencia(i + 2, "fecha", "Fecha vacía", fecha_raw)
                continue
            try:
                fecha = pd.to_datetime(str(fecha_raw), dayfirst=True)
                if fecha > hoy:
                    self._agregar_error(
                        i + 2, "fecha",
                        f"Fecha futura detectada: {fecha.strftime('%d/%m/%Y')}",
                        fecha_raw
                    )
            except Exception:
                self._agregar_error(
                    i + 2, "fecha",
                    f"Formato de fecha inválido: '{fecha_raw}'",
                    fecha_raw
                )

    # ── validaciones inteligentes ────────────

    def _detectar_proveedores_nuevos(self):
        """
        Simula detección de proveedores nuevos comparando frecuencia.
        Un proveedor que aparece 1 sola vez es 'nuevo' (heurística).
        """
        if "proveedor" not in self.df.columns:
            return
        conteo = self.df["proveedor"].value_counts()
        for proveedor, count in conteo.items():
            if count == 1 and str(proveedor).strip():
                fila = self.df[self.df["proveedor"] == proveedor].index[0] + 2
                self._agregar_advertencia(
                    fila, "proveedor",
                    f"Proveedor/cliente nuevo detectado: '{proveedor}' (aparece por primera vez en este archivo)",
                    proveedor
                )

    def _detectar_montos_anomalos(self):
        """
        Detecta montos que se desvían más de 3 desviaciones estándar del promedio.
        Clásico método estadístico Z-score.
        """
        if "total" not in self.df.columns:
            return
        totales = self.df["total"].apply(a_numero).dropna()
        if len(totales) < 5:
            return  # No hay suficientes datos para estadística

        media = totales.mean()
        std = totales.std()
        if std == 0:
            return

        for i, total in totales.items():
            z_score = abs((total - media) / std)
            if z_score > 3:
                self._agregar_advertencia(
                    i + 2, "total",
                    f"Monto atípico: ${total:,.0f} está {z_score:.1f} desviaciones estándar del promedio (${media:,.0f})",
                    total
                )

    def _detectar_cambio_brusco_totales(self):
        """
        Alerta si hay un salto mayor al 300% entre documentos consecutivos.
        Puede indicar un error de tipeo (ej: $100.000 vs $1.000.000).
        """
        if "total" not in self.df.columns:
            return
        totales = self.df["total"].apply(a_numero).dropna()
        if len(totales) < 3:
            return

        totales_list = totales.tolist()
        indices_list = totales.index.tolist()

        for j in range(1, len(totales_list)):
            prev = totales_list[j - 1]
            curr = totales_list[j]
            if prev == 0:
                continue
            ratio = abs(curr / prev)
            if ratio > 5 or ratio < 0.2:  # Cambio de más del 400%
                fila = indices_list[j] + 2
                self._agregar_advertencia(
                    fila, "total",
                    f"Cambio brusco de monto: de ${prev:,.0f} a ${curr:,.0f} (×{ratio:.1f}). Verifique si hay un error tipográfico.",
                    curr
                )

    def _detectar_patrones_rut_sospechosos(self):
        """
        Detecta RUTs que terminan en secuencias sospechosas o son repetitivos.
        Ej: 11111111-1 o 00000000-0 son RUTs de prueba.
        """
        if "rut" not in self.df.columns:
            return
        ruts_prueba = {"111111111", "000000000", "999999999"}
        for i, rut in self.df["rut"].items():
            rut_limpio = limpiar_rut(str(rut))
            if rut_limpio[:-1] in ruts_prueba:
                self._agregar_advertencia(
                    i + 2, "rut",
                    f"RUT sospechoso / de prueba detectado: {rut}",
                    rut
                )

    def _calcular_estadisticas(self) -> dict:
        """Genera estadísticas resumidas del libro."""
        stats: dict = {}
        if "total" in self.df.columns:
            totales = self.df["total"].apply(a_numero).dropna()
            stats["suma_total"] = float(totales.sum())
            stats["promedio_total"] = float(totales.mean()) if len(totales) > 0 else 0
            stats["cantidad_documentos"] = len(totales)

        if "iva" in self.df.columns:
            ivas = self.df["iva"].apply(a_numero).dropna()
            stats["suma_iva"] = float(ivas.sum())

        if "monto_neto" in self.df.columns:
            netos = self.df["monto_neto"].apply(a_numero).dropna()
            stats["suma_neta"] = float(netos.sum())

        return stats

    # ── análisis principal ───────────────────

    def analizar(self) -> dict:
        """
        Ejecuta todas las validaciones y retorna resultado estructurado.
        """
        # Ejecutar todas las validaciones
        self._validar_campos_requeridos()
        self._validar_ruts()
        self._validar_iva()
        self._validar_totales()
        self._validar_duplicados()
        self._validar_fechas()
        self._detectar_proveedores_nuevos()
        self._detectar_montos_anomalos()
        self._detectar_cambio_brusco_totales()
        self._detectar_patrones_rut_sospechosos()

        total_errores = len(self.errores)
        total_advertencias = len(self.advertencias)
        estado = "OK" if total_errores == 0 else "CON ERRORES"

        return {
            "resumen": {
                "estado": estado,
                "total_registros": len(self.df),
                "total_errores": total_errores,
                "total_advertencias": total_advertencias,
                "columnas_detectadas": self.columnas_disponibles,
                "columnas_normalizadas": list(self.df.columns),
                "estadisticas": self._calcular_estadisticas(),
                "analizado_en": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M:%S")
            },
            "errores": self.errores,
            "advertencias": self.advertencias
        }
