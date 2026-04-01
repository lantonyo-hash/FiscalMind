"""
FiscalMind - Backend principal
Pre-calculador y validador del Formulario 29 para contadores chilenos.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import archivos, f29, reporte

app = FastAPI(
    title="FiscalMind API",
    description="Pre-calculador y validador del F29 para Chile",
    version="2.0.0",
    docs_url="/docs",
)

# ── CORS ─────────────────────────────────────────────────────────
# En producción: reemplazar "*" con el dominio de Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────
app.include_router(archivos.router, prefix="/api/archivos", tags=["Archivos"])
app.include_router(f29.router,      prefix="/api/f29",      tags=["Formulario 29"])
app.include_router(reporte.router,  prefix="/api/reporte",  tags=["Reportes"])


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "app": "FiscalMind", "version": "2.0.0"}
