from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.order_state import OrderNotFound, TransicionInvalida


def registrar_manejadores_de_error(app: FastAPI) -> None:
    @app.exception_handler(TransicionInvalida)
    async def transicion_invalida(request: Request, error: TransicionInvalida):
        return JSONResponse(
            status_code=409,
            content={"detail": str(error), "estado_actual": error.actual},
        )

    @app.exception_handler(OrderNotFound)
    async def pedido_no_encontrado(request: Request, error: OrderNotFound):
        return JSONResponse(status_code=404, content={"detail": "No encontramos ese pedido"})
