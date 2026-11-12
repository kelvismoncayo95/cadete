import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.models import Order, User
from app.schemas.order import OrderDetailOut, RechazoIn
from app.services.dispatch import despachar_pedido
from app.services.order_state import cambiar_estado
from app.services.orders import detalle_pedido
from app.services.permissions import pedidos_visibles

router = APIRouter(prefix="/merchant", tags=["comercio"])


def cambiar_pedido_del_comercio(
    db: Session, usuario: User, order_id: uuid.UUID, destino: str, detalle: dict | None = None
) -> OrderDetailOut:
    # Primero: ¿es un pedido de MI comercio? Si no, para mí no existe (404).
    pedido = db.scalar(pedidos_visibles(usuario).where(Order.id == order_id))
    if pedido is None:
        raise HTTPException(404, "No encontramos ese pedido")
    cambiar_estado(db, pedido.id, destino, actor_user_id=usuario.id, detalle=detalle)
    db.commit()
    db.refresh(pedido)
    return detalle_pedido(db, pedido)


@router.post("/orders/{order_id}/accept", response_model=OrderDetailOut)
def aceptar(order_id: uuid.UUID, usuario: User = Depends(requiere_rol("merchant")), db: Session = Depends(get_db)):
    return cambiar_pedido_del_comercio(db, usuario, order_id, "aceptado")


@router.post("/orders/{order_id}/reject", response_model=OrderDetailOut)
def rechazar(
    order_id: uuid.UUID,
    datos: RechazoIn | None = None,
    usuario: User = Depends(requiere_rol("merchant")),
    db: Session = Depends(get_db),
):
    detalle = {"reason": datos.reason} if datos and datos.reason else None
    return cambiar_pedido_del_comercio(db, usuario, order_id, "rechazado", detalle)


@router.post("/orders/{order_id}/preparing", response_model=OrderDetailOut)
def preparando(order_id: uuid.UUID, usuario: User = Depends(requiere_rol("merchant")), db: Session = Depends(get_db)):
    return cambiar_pedido_del_comercio(db, usuario, order_id, "preparando")


@router.post("/orders/{order_id}/ready", response_model=OrderDetailOut)
def listo(order_id: uuid.UUID, usuario: User = Depends(requiere_rol("merchant")), db: Session = Depends(get_db)):
    resultado = cambiar_pedido_del_comercio(db, usuario, order_id, "listo")
    despachar_pedido(db, order_id)  # busca al repartidor enseguida; el trabajador reintenta si no hay
    db.commit()
    return resultado
