# FiscalMind v2 — Pre-calculador F29 Chile

Sistema SaaS para validación contable y pre-cálculo del Formulario 29.
Procesa 1 a 6 archivos Excel mensuales, detecta errores y genera el F29 listo para ingresar al SII.

---

## Arquitectura del sistema

```
fiscalmind/
├── backend/
│   ├── main.py                      # FastAPI app + CORS + routers
│   ├── requirements.txt
│   ├── models/
│   │   └── schemas.py               # Pydantic: todos los tipos del sistema
│   ├── routers/
│   │   ├── f29.py                   # POST /api/f29/calcular  ← endpoint principal
│   │   ├── archivos.py              # POST /api/archivos/validar
│   │   └── reporte.py               # POST /api/reporte/excel
│   └── services/
│       ├── ingesta.py               # Leer + normalizar Excel (pandas)
│       ├── validador.py             # Todas las validaciones contables
│       └── calculador_f29.py        # Lógica F29 + texto copiable
└── frontend/
    └── index.html                   # Dashboard completo (sin dependencias)
```

### Responsabilidades por capa

| Capa | Archivo | Responsabilidad |
|------|---------|-----------------|
| HTTP | `routers/f29.py` | Recibir archivos, validar metadatos, orquestar pipeline |
| Normalización | `services/ingesta.py` | Leer Excel/CSV, mapear columnas, agregar `periodo` y `tipo` |
| Validación | `services/validador.py` | Errores técnicos + anomalías inteligentes |
| Cálculo | `services/calculador_f29.py` | F29, resúmenes, texto copiable |
| Tipos | `models/schemas.py` | Pydantic: contratos de datos |

---

## Pipeline de procesamiento

```
Archivos Excel (1-6)
       │
       ▼
[ingesta.py] → unificar_archivos()
  - Leer xlsx/csv con pandas
  - Normalizar columnas (mapa flexible)
  - Agregar columnas: periodo | tipo
  - Concatenar en DataFrame único
       │
       ▼
[validador.py] → validar(df)
  - Campos vacíos
  - RUT módulo 11
  - IVA 19% (tolerancia ±$1)
  - Neto + IVA = Total
  - Facturas duplicadas (rut + numero_doc + periodo + tipo)
  - Proveedores nuevos (interpériodico)
  - Montos atípicos (Z-score > 3)
  - Variación interpériodica > 100% o < -60%
  - Cambios bruscos consecutivos (×5)
       │
       ▼
[calculador_f29.py] → calcular_f29(df)  ← solo si cero errores críticos
  - ventas_netas  = sum(monto_neto) donde tipo="ventas"
  - iva_debito    = sum(iva) donde tipo="ventas"
  - compras_netas = sum(monto_neto) donde tipo="compras"
  - iva_credito   = sum(iva) donde tipo="compras"
  - iva_determinado = max(0, debito - credito)
  - saldo_a_favor   = max(0, credito - debito)
  + generar_texto_copiable(f29)
       │
       ▼
RespuestaF29 (JSON)
  { estado, formulario_29, resumenes, incidencias, texto_copiable }
```

---

## Instalación y ejecución

### Backend (Render o local)

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Docs automáticas: http://localhost:8000/docs

### Frontend (Vercel o local)

```bash
# Opción A: abrir directo
open frontend/index.html

# Opción B: servidor simple
cd frontend && python -m http.server 3000
```

En producción, configurar la variable `API` en `index.html`:
```js
const API = "https://fiscalmind-api.onrender.com";
```

---

## API Reference

### POST /api/f29/calcular

Endpoint principal. Recibe archivos + metadatos, devuelve F29 completo.

**Request** (multipart/form-data):
```
archivos[]     File[]    Excel/CSV de compras o ventas
periodos[]     string[]  Período de cada archivo: YYYY-MM
tipos[]        string[]  "compras" o "ventas" (mismo orden que archivos)
periodo_declarado string  Opcional: YYYY-MM del período a declarar
```

**Response exitosa (200)**:
```json
{
  "estado": "OK",
  "formulario_29": {
    "periodo": "2025-06",
    "periodos_incluidos": ["2025-04", "2025-05", "2025-06"],
    "ventas_netas": 8200000,
    "iva_debito": 1558000,
    "compras_netas": 2720000,
    "iva_credito": 516800,
    "iva_determinado": 1041200,
    "saldo_a_favor": 0
  },
  "resumenes": [...],
  "incidencias": [],
  "texto_copiable": "╔══...",
  "analizado_en": "15/06/2025 14:32:01"
}
```

**Response con errores (200, estado CON_ERRORES)**:
```json
{
  "estado": "CON_ERRORES",
  "formulario_29": null,
  "incidencias": [
    {
      "tipo": "ERROR_CRITICO",
      "codigo": "IVA_INCORRECTO",
      "mensaje": "IVA inconsistente: declarado $200.000 pero debería ser $190.000 (19% de $1.000.000)",
      "fila": 4,
      "campo": "iva",
      "periodo": "2025-06",
      "valor": "200000"
    }
  ]
}
```

---

## Columnas soportadas (normalización automática)

| Estándar | Variantes reconocidas |
|----------|-----------------------|
| `fecha` | fecha, date, fecha_doc, fec, fecha_emision |
| `rut` | rut, rut_proveedor, rut_cliente, r.u.t, rut emisor |
| `proveedor` | proveedor, cliente, nombre, razon_social, emisor, receptor |
| `numero_doc` | numero_doc, folio, ndoc, n° doc, nro, folio_doc |
| `tipo_doc` | tipo, tipo_doc, tipo_documento, tdoc |
| `monto_neto` | neto, monto_neto, base_imponible, valor neto, afecto |
| `iva` | iva, monto_iva, impuesto, tax, i.v.a |
| `total` | total, monto_total, total_doc, valor_total |

---

## Validaciones implementadas

### Errores críticos (bloquean el F29)

| Código | Descripción |
|--------|-------------|
| `CAMPO_VACIO` | rut, monto_neto, iva o total vacíos |
| `RUT_INVALIDO` | Dígito verificador incorrecto (módulo 11) |
| `IVA_INCORRECTO` | IVA ≠ Neto × 19% (tolerancia ±$1) |
| `TOTAL_INCONSISTENTE` | Neto + IVA ≠ Total declarado |
| `FACTURA_DUPLICADA` | Mismo rut + numero_doc en mismo período/tipo |

### Advertencias inteligentes

| Código | Descripción |
|--------|-------------|
| `PROVEEDOR_NUEVO` | Proveedor no visto en períodos anteriores |
| `MONTO_ATIPICO` | Z-score > 3 desviaciones estándar |
| `VARIACION_INTERPERIODICA` | Cambio > 100% o < -60% entre meses |
| `CAMBIO_BRUSCO` | Ratio > 5x entre documentos consecutivos |

---

## Despliegue en producción

### Render (backend)

1. Crear servicio Web en Render
2. Apuntar al repositorio, directorio raíz: `backend/`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Agregar variable de entorno: `PYTHON_VERSION=3.11`

### Vercel (frontend)

1. Crear proyecto en Vercel
2. Framework Preset: Other
3. Output Directory: `frontend/`
4. Actualizar `const API = "https://tu-app.onrender.com"` en `index.html`

---

## Roadmap hacia SaaS completo

### Fase 3 — Autenticación y multiusuario
```
- fastapi-users + JWT
- PostgreSQL con SQLAlchemy (historial de análisis)
- Tabla de proveedores históricos por empresa/RUT
- Tier Free vs Pro
```

### Fase 4 — Inteligencia histórica real
```
- Comparar contra historial real del contribuyente
- Detección de anomalías entrenada con datos propios
- Alertas proactivas: "Este mes IVA cayó 40% vs mismo mes año anterior"
- Score de confianza del F29 (0-100)
```

### Fase 5 — Integración SII
```
- Conexión con API SII (cuando esté disponible)
- Descarga automática de folios autorizados
- Verificación cruzada facturas emitidas vs recibidas
- Pre-llenado automático del F29 en portal SII
```
