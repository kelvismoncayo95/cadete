"""Despacho: ofrecerle cada pedido listo al repartidor más cercano, de a uno.

Orden de bloqueos (siempre el mismo, para que no haya bloqueos cruzados): primero el PEDIDO,
después sus OFERTAS. La base de datos es la fuente de verdad: el trabajador solo llama a
estas funciones cada pocos segundos.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditLog, Courier, DispatchOffer, Order, OrderEvent
from app.services.couriers import buscar_repartidor_mas_cercano
from app.services.errors import ErrorDeNegocio
from app.services.order_state import cambiar_estado


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def despachar_pedido(db: Session, order_id: uuid.UUID, ahora: datetime | None = None) -> DispatchOffer | None:
    """Si el pedido está listo y nadie lo está atendiendo, le ofrece al siguiente repartidor.

    No hace commit: lo hace quien llama.
    """
    ahora = ahora or _ahora()
    pedido = db.get(Order, order_id, with_for_update=True)
    if pedido is None or pedido.status != "listo":
        return None
    previas = db.scalars(select(DispatchOffer).where(DispatchOffer.order_id == order_id)).all()
    if any(o.status == "pendiente" for o in previas):
        return None  # ya hay un repartidor pensándolo
    if len(previas) >= settings.max_ofertas_por_pedido:
        return None  # se agotaron los intentos
    candidato = buscar_repartidor_mas_cercano(
        db, pedido.merchant_id, excluir=[o.courier_id for o in previas]
    )
    if candidato is None:
        return None
    oferta = DispatchOffer(
        order_id=order_id,
        courier_id=candidato.courier.id,
        status="pendiente",
        distance_m=round(candidato.distancia_m),
        offered_at=ahora,
        expires_at=ahora + timedelta(seconds=settings.oferta_segundos),
    )
    db.add(oferta)
    db.flush()
    return oferta


def responder_oferta(
    db: Session, offer_id: uuid.UUID, user_id: uuid.UUID, aceptar: bool, ahora: datetime | None = None
) -> DispatchOffer:
    """El repartidor acepta o rechaza. Hace commit (salvo que lance TransicionInvalida)."""
    ahora = ahora or _ahora()
    oferta = db.get(DispatchOffer, offer_id)
    repartidor = db.get(Courier, oferta.courier_id) if oferta else None
    if oferta is None or repartidor.user_id != user_id:
        raise ErrorDeNegocio(404, "No encontramos esa oferta")

    db.get(Order, oferta.order_id, with_for_update=True)  # primero el pedido...
    db.refresh(oferta, with_for_update=True)              # ...y después la oferta
    if oferta.status != "pendiente":
        raise ErrorDeNegocio(409, "Esta oferta ya no está disponible")

    if oferta.expires_at <= ahora:
        oferta.status = "expirada"
        db.flush()
        despachar_pedido(db, oferta.order_id, ahora)
        db.commit()
        raise ErrorDeNegocio(409, "No respondiste a tiempo: la oferta pasó a otro repartidor")

    oferta.responded_at = ahora
    if aceptar:
        # Falla con TransicionInvalida si el pedido ya no está "listo" (por ejemplo, cancelado).
        cambiar_estado(db, oferta.order_id, "asignado", actor_user_id=user_id)
        db.get(Order, oferta.order_id).courier_id = repartidor.id
        repartidor.status = "busy"
        oferta.status = "aceptada"
    else:
        oferta.status = "rechazada"
        db.flush()
        despachar_pedido(db, oferta.order_id, ahora)  # pasa al siguiente enseguida
    db.commit()
    return oferta


def expirar_ofertas(db: Session, ahora: datetime | None = None) -> int:
    """Marca como expiradas las ofertas vencidas y ofrece cada pedido al siguiente repartidor."""
    ahora = ahora or _ahora()
    pedidos = db.scalars(
        select(DispatchOffer.order_id)
        .where(DispatchOffer.status == "pendiente", DispatchOffer.expires_at <= ahora)
        .distinct()
    ).all()
    total = 0
    for order_id in pedidos:
        # Primero el pedido (si otro lo está tocando, se deja para la próxima vuelta).
        bloqueado = db.scalar(select(Order.id).where(Order.id == order_id).with_for_update(skip_locked=True))
        if bloqueado is None:
            continue
        vencidas = db.scalars(
            select(DispatchOffer)
            .where(
                DispatchOffer.order_id == order_id,
                DispatchOffer.status == "pendiente",
                DispatchOffer.expires_at <= ahora,
            )
            .with_for_update()
        ).all()
        for oferta in vencidas:
            oferta.status = "expirada"
        db.flush()
        despachar_pedido(db, order_id, ahora)
        db.commit()
        total += len(vencidas)
    return total


def reintentar_despachos(db: Session, ahora: datetime | None = None) -> int:
    """Pedidos listos que nadie está atendiendo: intenta ofrecerlos. Devuelve cuántas ofertas creó."""
    ahora = ahora or _ahora()
    cantidad_de_ofertas = (
        select(func.count()).select_from(DispatchOffer).where(DispatchOffer.order_id == Order.id).scalar_subquery()
    )
    candidatos = db.scalars(
        select(Order.id).where(
            Order.status == "listo",
            ~exists().where(DispatchOffer.order_id == Order.id, DispatchOffer.status == "pendiente"),
            cantidad_de_ofertas < settings.max_ofertas_por_pedido,
        )
    ).all()
    creadas = 0
    for order_id in candidatos:
        if despachar_pedido(db, order_id, ahora) is not None:
            creadas += 1
        db.commit()
    return creadas


def avisar_pedidos_sin_repartidor(db: Session, ahora: datetime | None = None) -> int:
    """A los 10 minutos de estar listo sin repartidor, deja un aviso para el comercio (una sola vez)."""
    ahora = ahora or _ahora()
    limite = ahora - timedelta(minutes=settings.aviso_sin_repartidor_minutos)
    filas = db.execute(
        select(Order.id, func.max(OrderEvent.created_at))
        .join(OrderEvent, OrderEvent.order_id == Order.id)
        .where(Order.status == "listo", OrderEvent.to_status == "listo")
        .group_by(Order.id)
    ).all()
    avisados = 0
    for order_id, listo_desde in filas:
        if listo_desde > limite:
            continue
        ya_avisado = db.scalar(
            select(exists().where(AuditLog.action == "sin_repartidor", AuditLog.entity_id == str(order_id)))
        )
        if ya_avisado:
            continue
        db.add(AuditLog(
            action="sin_repartidor", entity="order", entity_id=str(order_id),
            detail={"listo_desde": listo_desde.isoformat()},
        ))
        avisados += 1
    db.commit()
    return avisados
