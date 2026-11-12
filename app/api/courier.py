import uuid
from datetime import datetime, timezone
from typing import Literal

import redis
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import Courier, DispatchOffer, Merchant, Order, User
from app.schemas.courier import OfertaOut
from app.schemas.order import OrderDetailOut
from app.services.couriers import actualizar_posicion
from app.services.dispatch import responder_oferta
from app.services.errors import ErrorDeNegocio
from app.services.order_state import cambiar_estado
from app.services.orders import detalle_pedido
from app.services.permissions import pedidos_visibles

router = APIRouter(prefix="/courier", tags=["repartidor"])


class PosicionIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class EstadoIn(BaseModel):
    status: Literal["available", "offline"]


def _mi_repartidor(db: Session, usuario: User) -> Courier:
    repartidor = db.scalar(select(Courier).where(Courier.user_id == usuario.id))
    if repartidor is None:
        raise HTTPException(404, "No encontramos tu perfil de repartidor")
    return repartidor


@router.post("/location", status_code=204)
def enviar_posicion(
    datos: PosicionIn,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> Response:
    actualizar_posicion(db, r, _mi_repartidor(db, usuario), datos.lat, datos.lon)
    return Response(status_code=204)


@router.post("/status")
def cambiar_estado_del_repartidor(
    datos: EstadoIn,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
):
    repartidor = _mi_repartidor(db, usuario)
    if repartidor.status == "busy":
        raise ErrorDeNegocio(409, "Tenés un pedido en curso: terminá la entrega primero")
    repartidor.status = datos.status
    db.commit()
    return {"status": repartidor.status}


@router.get("/offers", response_model=list[OfertaOut])
def mis_ofertas(usuario: User = Depends(requiere_rol("courier")), db: Session = Depends(get_db)):
    repartidor = _mi_repartidor(db, usuario)
    ahora = datetime.now(timezone.utc)
    filas = db.execute(
        select(DispatchOffer, Order, Merchant)
        .join(Order, Order.id == DispatchOffer.order_id)
        .join(Merchant, Merchant.id == Order.merchant_id)
        .where(
            DispatchOffer.courier_id == repartidor.id,
            DispatchOffer.status == "pendiente",
            DispatchOffer.expires_at > ahora,
        )
        .order_by(DispatchOffer.offered_at)
    ).all()
    return [
        OfertaOut(
            id=o.id, order_id=p.id, merchant_name=m.name, merchant_address=m.address,
            delivery_address=p.delivery_address, distance_m=o.distance_m,
            fee_cents=p.delivery_fee_cents, expires_at=o.expires_at,
            seconds_left=max(0, int((o.expires_at - ahora).total_seconds())),
        )
        for o, p, m in filas
    ]


@router.post("/offers/{offer_id}/accept", response_model=OrderDetailOut)
def aceptar_oferta(
    offer_id: uuid.UUID, usuario: User = Depends(requiere_rol("courier")), db: Session = Depends(get_db)
):
    oferta = responder_oferta(db, offer_id, usuario.id, aceptar=True)
    return detalle_pedido(db, db.get(Order, oferta.order_id))


@router.post("/offers/{offer_id}/reject")
def rechazar_oferta(
    offer_id: uuid.UUID, usuario: User = Depends(requiere_rol("courier")), db: Session = Depends(get_db)
):
    responder_oferta(db, offer_id, usuario.id, aceptar=False)
    return {"status": "rechazada"}


def _mi_pedido(db: Session, usuario: User, order_id: uuid.UUID) -> Order:
    pedido = db.scalar(pedidos_visibles(usuario).where(Order.id == order_id))
    if pedido is None:
        raise HTTPException(404, "No encontramos ese pedido")
    return pedido


@router.post("/orders/{order_id}/picked-up", response_model=OrderDetailOut)
def retire_el_pedido(
    order_id: uuid.UUID, usuario: User = Depends(requiere_rol("courier")), db: Session = Depends(get_db)
):
    pedido = _mi_pedido(db, usuario, order_id)
    cambiar_estado(db, pedido.id, "en_camino", actor_user_id=usuario.id)
    db.commit()
    db.refresh(pedido)
    return detalle_pedido(db, pedido)


@router.post("/orders/{order_id}/delivered", response_model=OrderDetailOut)
def entregue_el_pedido(
    order_id: uuid.UUID, usuario: User = Depends(requiere_rol("courier")), db: Session = Depends(get_db)
):
    pedido = _mi_pedido(db, usuario, order_id)
    cambiar_estado(db, pedido.id, "entregado", actor_user_id=usuario.id)
    _mi_repartidor(db, usuario).status = "available"  # queda libre para el próximo pedido
    db.commit()
    db.refresh(pedido)
    return detalle_pedido(db, pedido)
