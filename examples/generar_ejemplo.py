"""
Genera archivo Excel de ejemplo con datos chilenos reales + errores intencionales
para demostrar las capacidades del Revisor Contable Inteligente.
"""

import pandas as pd
from pathlib import Path

data = [
    # Facturas normales correctas
    {
        "fecha": "01/03/2025",
        "rut": "76.123.456-7",
        "proveedor": "Distribuidora Pérez Ltda.",
        "numero_doc": "F-001234",
        "tipo_doc": "Factura",
        "monto_neto": 1000000,
        "iva": 190000,
        "total": 1190000,
    },
    {
        "fecha": "03/03/2025",
        "rut": "12.345.678-9",
        "proveedor": "Servicios TI SpA",
        "numero_doc": "F-005678",
        "tipo_doc": "Factura",
        "monto_neto": 500000,
        "iva": 95000,
        "total": 595000,
    },
    {
        "fecha": "05/03/2025",
        "rut": "77.890.123-4",
        "proveedor": "Comercial Andina SA",
        "numero_doc": "F-009012",
        "tipo_doc": "Factura",
        "monto_neto": 250000,
        "iva": 47500,
        "total": 297500,
    },
    # ERROR: IVA INCORRECTO (debería ser 190.000 pero dice 200.000)
    {
        "fecha": "07/03/2025",
        "rut": "76.543.210-K",
        "proveedor": "Papelería Central",
        "numero_doc": "F-003456",
        "tipo_doc": "Factura",
        "monto_neto": 1000000,
        "iva": 200000,  # ← ERROR: IVA mal calculado
        "total": 1200000,
    },
    # ERROR: FACTURA DUPLICADA
    {
        "fecha": "10/03/2025",
        "rut": "76.123.456-7",
        "proveedor": "Distribuidora Pérez Ltda.",
        "numero_doc": "F-001234",  # ← DUPLICADO
        "tipo_doc": "Factura",
        "monto_neto": 1000000,
        "iva": 190000,
        "total": 1190000,
    },
    # ERROR: RUT INVÁLIDO
    {
        "fecha": "12/03/2025",
        "rut": "12.345.678-0",  # ← DV incorrecto (debería ser 9)
        "proveedor": "Proveedor Desconocido",
        "numero_doc": "F-007890",
        "tipo_doc": "Factura",
        "monto_neto": 300000,
        "iva": 57000,
        "total": 357000,
    },
    # ERROR: TOTAL INCONSISTENTE
    {
        "fecha": "14/03/2025",
        "rut": "96.789.012-3",
        "proveedor": "Seguros del Sur",
        "numero_doc": "F-011234",
        "tipo_doc": "Factura",
        "monto_neto": 800000,
        "iva": 152000,
        "total": 999999,  # ← ERROR: no cuadra con neto+iva
    },
    # ADVERTENCIA: PROVEEDOR NUEVO (aparece 1 vez)
    {
        "fecha": "18/03/2025",
        "rut": "89.012.345-6",
        "proveedor": "Nuevo Proveedor Desconocido XYZ",
        "numero_doc": "F-015678",
        "tipo_doc": "Factura",
        "monto_neto": 400000,
        "iva": 76000,
        "total": 476000,
    },
    # ADVERTENCIA: MONTO ATÍPICO (10x el promedio)
    {
        "fecha": "20/03/2025",
        "rut": "76.234.567-8",
        "proveedor": "Gran Contrato Excep. SA",
        "numero_doc": "F-019012",
        "tipo_doc": "Factura",
        "monto_neto": 50000000,  # ← 50 millones, muy atípico
        "iva": 9500000,
        "total": 59500000,
    },
    # Factura normal de cierre
    {
        "fecha": "28/03/2025",
        "rut": "76.123.456-7",
        "proveedor": "Distribuidora Pérez Ltda.",
        "numero_doc": "F-021001",
        "tipo_doc": "Factura",
        "monto_neto": 750000,
        "iva": 142500,
        "total": 892500,
    },
]

df = pd.DataFrame(data)
path = Path(__file__).parent / "libro_compras_marzo_2025_ejemplo.xlsx"
df.to_excel(path, index=False)
print(f"✅ Archivo creado: {path}")
print(f"   {len(df)} registros con errores y advertencias intencionales")
print("\nErrores intencionales incluidos:")
print("  - Fila 4: IVA incorrecto (200.000 en vez de 190.000)")
print("  - Filas 1 y 5: Factura duplicada (F-001234)")
print("  - Fila 6: RUT con DV inválido")
print("  - Fila 7: Total que no cuadra con neto+IVA")
print("  - Fila 8: Proveedor nuevo detectado")
print("  - Fila 9: Monto atípico ($50.000.000)")
