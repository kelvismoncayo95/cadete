from fastapi import FastAPI

from app.api import auth, orders
from app.api.errors import registrar_manejadores_de_error

app = FastAPI(title="Cadete", description="Pedidos y reparto en Montevideo (datos inventados)")

registrar_manejadores_de_error(app)
app.include_router(auth.router)
app.include_router(orders.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
