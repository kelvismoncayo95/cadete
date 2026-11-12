import uuid

import redis
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol, usuario_actual
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import Order, User
from app.schemas.order import OrderCreateIn, OrderDetailOut, OrderOut
from app.services.orders import crear_pedido, detalle_pedido
from app.services.permissions import pedidos_visibles

router = APIRouter(tags=["pedidos"])


@router.post("/orders", status_code=201, response_model=OrderDetailOut)
def crear(
    datos: OrderCreateIn,
    idempotency_key: str | None = Header(default=None),
    usuario: User = Depends(requiere_rol("customer")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    estado, cuerpo, repetido = crear_pedido(db, r, usuario, datos, idempotency_key)
    respuesta = JSONResponse(status_code=estado, content=cuerpo)
    if repetido:
        respuesta.headers["Idempotent-Replay"] = "true"
    return respuesta


@router.get("/orders", response_model=list[OrderOut])
def mis_pedidos(usuario: User = Depends(usuario_actual), db: Session = Depends(get_db)):
    consulta = pedidos_visibles(usuario).order_by(Order.created_at.desc())
    return db.scalars(consulta).all()


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def un_pedido(
    order_id: uuid.UUID,
    usuario: User = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    pedido = db.scalar(pedidos_visibles(usuario).where(Order.id == order_id))
    if pedido is None:
        raise HTTPException(404, "No encontramos ese pedido")
    return detalle_pedido(db, pedido)
