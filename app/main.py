from fastapi import FastAPI

app = FastAPI(title="Cadete", description="Pedidos y reparto en Montevideo (datos inventados)")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
