import uuid

import redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import AuditLog, Order, User
from app.schemas.order import OrderDetailOut, RechazoIn
from app.services.dispatch import despachar_pedido
from app.services.events import publicar_estado
from app.services.order_state import cambiar_estado
from app.services.orders import detalle_pedido
from app.services.permissions import pedidos_visibles

router = APIRouter(prefix="/merchant", tags=["comercio"])


def cambiar_pedido_del_comercio(
    db: Session, r: redis.Redis, usuario: User, order_id: uuid.UUID, destino: str, detalle: dict | None = None
) -> OrderDetailOut:
    # Primero: ¿es un pedido de MI comercio? Si no, para mí no existe (404).
    pedido = db.scalar(pedidos_visibles(usuario).where(Order.id == order_id))
    if pedido is None:
        raise HTTPException(404, "No encontramos ese pedido")
    cambiar_estado(db, pedido.id, destino, actor_user_id=usuario.id, detalle=detalle)
    db.commit()
    publicar_estado(db, r, pedido.id)
    db.refresh(pedido)
    return detalle_pedido(db, pedido)


@router.post("/orders/{order_id}/accept", response_model=OrderDetailOut)
def aceptar(order_id: uuid.UUID, usuario: User = Depends(requiere_rol("merchant")), db: Session = Depends(get_db), r: redis.Redis = Depends(get_redis)):
    return cambiar_pedido_del_comercio(db, r, usuario, order_id, "aceptado")


@router.post("/orders/{order_id}/reject", response_model=OrderDetailOut)
def rechazar(
    order_id: uuid.UUID,
    datos: RechazoIn | None = None,
    usuario: User = Depends(requiere_rol("merchant")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    detalle = {"reason": datos.reason} if datos and datos.reason else None
    return cambiar_pedido_del_comercio(db, r, usuario, order_id, "rechazado", detalle)


@router.post("/orders/{order_id}/preparing", response_model=OrderDetailOut)
def preparando(order_id: uuid.UUID, usuario: User = Depends(requiere_rol("merchant")), db: Session = Depends(get_db), r: redis.Redis = Depends(get_redis)):
    return cambiar_pedido_del_comercio(db, r, usuario, order_id, "preparando")


@router.post("/orders/{order_id}/ready", response_model=OrderDetailOut)
def listo(order_id: uuid.UUID, usuario: User = Depends(requiere_rol("merchant")), db: Session = Depends(get_db), r: redis.Redis = Depends(get_redis)):
    resultado = cambiar_pedido_del_comercio(db, r, usuario, order_id, "listo")
    despachar_pedido(db, order_id)  # busca al repartidor enseguida; el trabajador reintenta si no hay
    db.commit()
    return resultado


@router.get("/alerts")
def alertas(usuario: User = Depends(requiere_rol("merchant")), db: Session = Depends(get_db)):
    """Pedidos listos que llevan 10 minutos o más sin repartidor (el trabajador deja el aviso)."""
    ids = db.scalars(
        pedidos_visibles(usuario).where(Order.status == "listo").with_only_columns(Order.id)
    ).all()
    avisados = set(db.scalars(
        select(AuditLog.entity_id).where(AuditLog.action == "sin_repartidor", AuditLog.entity_id.in_([str(i) for i in ids]))
    ))
    return [{"order_id": str(i), "type": "sin_repartidor"} for i in ids if str(i) in avisados]
