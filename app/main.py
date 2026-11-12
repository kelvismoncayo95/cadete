from fastapi import FastAPI

from app.api import auth, catalog, courier, demo, live, merchant, orders
from app.api.errors import registrar_manejadores_de_error

app = FastAPI(title="Cadete", description="Pedidos y reparto en Montevideo (datos inventados)")

registrar_manejadores_de_error(app)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(courier.router)
app.include_router(demo.router)
app.include_router(merchant.router)
app.include_router(live.router)
app.include_router(orders.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
