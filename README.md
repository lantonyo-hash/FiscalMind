# Revisor Contable Inteligente 🧾

MVP de validación automática de libros contables chilenos.
Detecta errores de IVA, RUTs inválidos, facturas duplicadas y anomalías antes de declarar al SII.

---

## Estructura del proyecto

```
revisor-contable/
├── backend/
│   ├── main.py          # FastAPI: rutas /analizar y /descargar-reporte
│   ├── analyzer.py      # Motor de validaciones contables
│   └── requirements.txt
├── frontend/
│   └── index.html       # Dashboard completo (HTML + JS puro, sin dependencias)
├── examples/
│   ├── generar_ejemplo.py                    # Script para crear Excel de prueba
│   └── libro_compras_marzo_2025_ejemplo.xlsx # (generado por el script)
└── README.md
```

---

## Instalación rápida

### 1. Backend (Python)

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API disponible en: http://localhost:8000
Docs automáticas: http://localhost:8000/docs

### 2. Frontend

```bash
# Opción A: abrir directo en browser
open frontend/index.html

# Opción B: servidor simple
cd frontend && python -m http.server 3000
```

### 3. Generar datos de prueba

```bash
cd examples
python generar_ejemplo.py
```

---

## API endpoints

### POST /analizar
Recibe archivo Excel/CSV, retorna JSON con errores y advertencias.

```bash
curl -X POST http://localhost:8000/analizar \
  -F "file=@libro_compras_marzo_2025_ejemplo.xlsx"
```

Respuesta ejemplo:
```json
{
  "resumen": {
    "estado": "CON ERRORES",
    "total_registros": 10,
    "total_errores": 5,
    "total_advertencias": 3,
    "estadisticas": {
      "suma_neta": 55300000,
      "suma_iva": 10302500,
      "suma_total": 65602500
    }
  },
  "errores": [
    {
      "fila": 4,
      "campo": "iva",
      "tipo": "ERROR CRÍTICO",
      "mensaje": "IVA inconsistente: declarado $200.000 pero debería ser $190.000 (19% de $1.000.000)",
      "valor": "200000"
    },
    ...
  ],
  "advertencias": [
    {
      "fila": 8,
      "campo": "proveedor",
      "tipo": "ADVERTENCIA",
      "mensaje": "Proveedor nuevo detectado: 'Nuevo Proveedor XYZ'",
      "valor": "Nuevo Proveedor XYZ"
    },
    ...
  ]
}
```

### POST /descargar-reporte
Mismo input que /analizar, descarga Excel con 4 hojas:
- Resumen, Errores Críticos, Advertencias, Datos Originales

---

## Validaciones implementadas

### Errores críticos (bloquean declaración)
| Validación              | Descripción                                           |
|-------------------------|-------------------------------------------------------|
| IVA 19%                 | Verifica que IVA = Neto × 0.19 (tolerancia ±$1)      |
| Cuadre neto+IVA=total   | Detecta totales que no cuadran con sus componentes    |
| Facturas duplicadas     | Detecta mismo RUT + número de documento               |
| RUT inválido            | Algoritmo módulo 11 para dígito verificador           |
| Campos obligatorios     | Detecta celdas vacías en rut, montos, IVA, total      |
| Fecha futura            | Alerta si la fecha del documento es posterior a hoy   |
| Fecha inválida          | Detecta formatos incorrectos de fecha                 |

### Advertencias inteligentes (requieren revisión)
| Validación              | Descripción                                           |
|-------------------------|-------------------------------------------------------|
| Proveedor nuevo         | Aparece solo 1 vez en el archivo (posible error)      |
| Monto atípico           | Z-score > 3 respecto al promedio del archivo          |
| Cambio brusco           | Ratio > 5x entre documentos consecutivos              |
| RUT de prueba           | Detecta RUTs como 111111111 o 000000000               |

---

## Columnas soportadas (normalización automática)

El sistema reconoce variantes de nombres de columnas:

| Estándar interno | Variantes aceptadas |
|------------------|---------------------|
| `fecha`          | fecha, date, fecha_doc, fec |
| `rut`            | rut, rut_proveedor, rut_cliente, r.u.t |
| `proveedor`      | proveedor, cliente, nombre, razon_social, emisor |
| `numero_doc`     | numero_doc, folio, ndoc, n° doc, nro |
| `monto_neto`     | neto, monto_neto, base_imponible, valor neto |
| `iva`            | iva, monto_iva, impuesto, tax |
| `total`          | total, monto_total, total_doc, valor_total |

---

## Roadmap SaaS (escalabilidad)

### Fase 2 - Multiusuario
```
- Auth con JWT (fastapi-users)
- Base de datos PostgreSQL para guardar historial
- Multi-tenancy por empresa/RUT
- Dashboard de tendencias mensuales
```

### Fase 3 - Inteligencia real
```
- Historial de proveedores por cliente (detectar cambios reales)
- ML para detección de anomalías entrenado con datos históricos
- Integración con API del SII (cuando esté disponible)
- Comparación automática libro de compras vs facturas recibidas
```

### Fase 4 - Integración directa
```
- API REST para que RJC Software u otros sistemas envíen datos automáticamente
- Webhooks para notificar al contador cuando hay errores
- Exportación directa al formato del SII (F29, F22)
```

---

## Datos de prueba incluidos

El archivo de ejemplo `libro_compras_marzo_2025_ejemplo.xlsx` tiene 10 registros con:
- 2 facturas normales correctas
- 1 IVA incorrecto ($200.000 en vez de $190.000)
- 1 par de facturas duplicadas (F-001234)
- 1 RUT con dígito verificador incorrecto
- 1 total que no cuadra
- 1 proveedor nuevo detectado
- 1 monto atípico ($50.000.000)
