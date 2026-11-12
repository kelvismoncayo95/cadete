from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import auth, catalog, courier, demo, live, merchant, ops, orders
from app.core.observability import ObservabilidadMiddleware, configurar_logs
from app.api.errors import registrar_manejadores_de_error

configurar_logs()
app = FastAPI(title="Cadete", description="Pedidos y reparto en Montevideo (datos inventados)")

registrar_manejadores_de_error(app)
app.add_middleware(ObservabilidadMiddleware)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(courier.router)
app.include_router(demo.router)
app.include_router(merchant.router)
app.include_router(live.router)
app.include_router(ops.router)
app.include_router(orders.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# La web (HTML, CSS, JS, mapa) se sirve desde la misma app. Va al FINAL: las rutas de la API tienen prioridad.
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
