from fastapi import FastAPI

from app.api.errors import registrar_manejadores_de_error

app = FastAPI(title="Cadete", description="Pedidos y reparto en Montevideo (datos inventados)")

registrar_manejadores_de_error(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
