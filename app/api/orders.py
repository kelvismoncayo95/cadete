import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_actual
from app.core.database import get_db
from app.models import Order, User
from app.schemas.order import OrderOut
from app.services.permissions import pedidos_visibles

router = APIRouter(tags=["pedidos"])


@router.get("/orders", response_model=list[OrderOut])
def mis_pedidos(usuario: User = Depends(usuario_actual), db: Session = Depends(get_db)):
    consulta = pedidos_visibles(usuario).order_by(Order.created_at.desc())
    return db.scalars(consulta).all()


@router.get("/orders/{order_id}", response_model=OrderOut)
def un_pedido(
    order_id: uuid.UUID,
    usuario: User = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    pedido = db.scalar(pedidos_visibles(usuario).where(Order.id == order_id))
    if pedido is None:
        raise HTTPException(404, "No encontramos ese pedido")
    return pedido
