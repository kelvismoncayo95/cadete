import uuid
from datetime import datetime, timezone
from typing import Literal

import redis
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, literal, select
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import Courier, DispatchOffer, Merchant, Order, User
from app.schemas.courier import ComercioPreparandoOut, OfertaOut
from app.schemas.order import OrderDetailOut
from app.services.couriers import actualizar_posicion
from app.services.dispatch import responder_oferta
from app.services.errors import ErrorDeNegocio
from app.services.entrega import entregar, llegar_al_comercio, retirar
from app.services.events import coordenadas_del_pedido, publicar_estado, publicar_posicion
from app.services.pagos import calcular_pago_repartidor
from app.services.orders import detalle_pedido
from app.services.routing import get_router
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
    repartidor = _mi_repartidor(db, usuario)
    lat, lon = datos.lat, datos.lon
    ajuste = get_router().ajustar((lat, lon))
    if ajuste is not None:
        if ajuste[1] > settings.max_distancia_a_calle_m:
            raise ErrorDeNegocio(422, "Ese punto no está sobre una calle. Tocá un punto más cerca de una calle.")
        (lat, lon), _ = ajuste   # la moto queda ENCIMA de la calle
    actualizar_posicion(db, r, repartidor, lat, lon)
    publicar_posicion(db, r, repartidor, lat, lon)
    return Response(status_code=204)


@router.get("/status")
def mi_estado(usuario: User = Depends(requiere_rol("courier")), db: Session = Depends(get_db)):
    """Mi estado y mi última posición (la pantalla del repartidor la dibuja al abrirse)."""
    repartidor = _mi_repartidor(db, usuario)
    geometria = cast(Courier.last_location, Geometry)
    lat, lon = db.execute(
        select(func.ST_Y(geometria), func.ST_X(geometria)).where(Courier.id == repartidor.id)
    ).one()
    return {"status": repartidor.status, "lat": lat, "lon": lon}


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
    ofertas = []
    for o, p, m in filas:
        c = coordenadas_del_pedido(db, p.id)
        entrega_m = get_router().ruta([(c["mlat"], c["mlon"]), (c["dlat"], c["dlon"])]).distancia_m
        ofertas.append(OfertaOut(
            id=o.id, order_id=p.id, merchant_name=m.name, merchant_address=m.address,
            delivery_address=p.delivery_address, distance_m=o.distance_m,
            pay_cents=calcular_pago_repartidor(o.distance_m or 0, entrega_m),
            pickup_m=o.distance_m, delivery_m=round(entrega_m),
            expires_at=o.expires_at, seconds_left=max(0, int((o.expires_at - ahora).total_seconds())),
        ))
    return ofertas


@router.get("/preparing", response_model=list[ComercioPreparandoOut])
def comercios_preparando(usuario: User = Depends(requiere_rol("courier")), db: Session = Depends(get_db)):
    """Los comercios que tienen pedidos en preparación o listos sin repartidor, con su distancia a mí.

    Sirve para que el repartidor sepa de qué comercio le puede llegar una oferta (las ofertas salen
    cuando el comercio marca «listo», y solo a los repartidores a menos de 5 km)."""
    repartidor = _mi_repartidor(db, usuario)
    filas = db.execute(
        select(
            Merchant.id, Merchant.name, Merchant.address,
            func.ST_Y(cast(Merchant.location, Geometry)), func.ST_X(cast(Merchant.location, Geometry)),
            func.count(Order.id), func.bool_or(Order.status == "listo"),
            func.ST_Distance(Merchant.location, repartidor.last_location) if repartidor.last_location is not None else literal(None),
        )
        .join(Order, Order.merchant_id == Merchant.id)
        .where(Order.status.in_(["aceptado", "preparando", "listo"]))
        .group_by(Merchant.id)
    ).all()
    salida = [
        ComercioPreparandoOut(
            merchant_id=i, name=n, address=d, lat=lat, lon=lon, orders=cant,
            status="listo" if hay_listo else "preparando", distance_m=None if dist is None else round(dist),
        )
        for i, n, d, lat, lon, cant, hay_listo, dist in filas
    ]
    return sorted(salida, key=lambda c: (c.distance_m is None, c.distance_m or 0))


@router.post("/offers/{offer_id}/accept", response_model=OrderDetailOut)
def aceptar_oferta(
    offer_id: uuid.UUID,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    oferta = responder_oferta(db, offer_id, usuario.id, aceptar=True)
    publicar_estado(db, r, oferta.order_id)
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


@router.post("/orders/{order_id}/arrived", response_model=OrderDetailOut)
def llegue_al_comercio(
    order_id: uuid.UUID,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """«Llegué al comercio»: solo se acepta si estás a menos de 25 m (del comercio o de su calle)."""
    pedido = _mi_pedido(db, usuario, order_id)
    llegar_al_comercio(db, pedido, usuario.id)
    db.commit()
    publicar_estado(db, r, pedido.id)
    db.refresh(pedido)
    return detalle_pedido(db, pedido)


@router.post("/orders/{order_id}/picked-up", response_model=OrderDetailOut)
def retire_el_pedido(
    order_id: uuid.UUID,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """«Retiré el pedido»: solo después de haber marcado la llegada al comercio."""
    pedido = _mi_pedido(db, usuario, order_id)
    retirar(db, pedido, usuario.id)
    db.commit()
    publicar_estado(db, r, pedido.id)
    db.refresh(pedido)
    return detalle_pedido(db, pedido)


@router.post("/orders/{order_id}/delivered", response_model=OrderDetailOut)
def entregue_el_pedido(
    order_id: uuid.UUID,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """«Entregué el pedido»: solo a menos de 25 m del cliente. Al entregar se cobra y se paga a todos."""
    pedido = _mi_pedido(db, usuario, order_id)
    entregar(db, pedido, usuario.id)
    db.commit()
    publicar_estado(db, r, pedido.id)
    db.refresh(pedido)
    return detalle_pedido(db, pedido)


class PilotoIn(BaseModel):
    activo: bool


@router.post("/autopilot", status_code=204)
def piloto_automatico(
    datos: PilotoIn,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> Response:
    """Demo: el simulador conduce la moto de este repartidor por las calles hacia su próximo destino.

    No marca ningún paso: llegar, retirar y entregar los hace la persona con los botones."""
    clave = f"autopilot:{_mi_repartidor(db, usuario).id}"
    if datos.activo:
        r.set(clave, "1", ex=900)
    else:
        r.delete(clave)
    return Response(status_code=204)
