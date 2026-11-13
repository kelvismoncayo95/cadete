import hashlib
import json
import uuid
from typing import Any

import redis
from fastapi.encoders import jsonable_encoder
from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.zone import dentro_de_montevideo
from app.models import IdempotencyKey, Merchant, Order, OrderEvent, OrderItem, Product, User
from app.schemas.order import ItemOut, OrderCreateIn, OrderDetailOut
from app.services.errors import ErrorDeNegocio
from app.services.routing import get_router
from app.services.rate_limit import bloqueado, registrar_fallo


def detalle_pedido(db: Session, pedido: Order) -> OrderDetailOut:
    items = db.scalars(select(OrderItem).where(OrderItem.order_id == pedido.id).order_by(OrderItem.id))
    return OrderDetailOut(
        **{c: getattr(pedido, c) for c in (
            "id", "status", "merchant_id", "courier_id", "delivery_address",
            "subtotal_cents", "delivery_fee_cents", "total_cents", "courier_pay_cents", "created_at",
        )},
        items=[ItemOut(name=i.name_snapshot, unit_price_cents=i.unit_price_cents, quantity=i.quantity) for i in items],
    )


def _huella(datos: OrderCreateIn) -> str:
    """Resumen del pedido pedido: sirve para saber si dos pedidos con la misma clave son el mismo."""
    canonico = json.dumps(datos.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonico.encode()).hexdigest()


def _validar(db: Session, datos: OrderCreateIn) -> tuple[Merchant, dict[uuid.UUID, Product]]:
    if not datos.items:
        raise ErrorDeNegocio(422, "Elegí al menos un producto")
    if any(not 1 <= i.quantity <= 20 for i in datos.items):
        raise ErrorDeNegocio(422, "Podés pedir entre 1 y 20 unidades de cada producto")
    ids = [i.product_id for i in datos.items]
    if len(set(ids)) != len(ids):
        raise ErrorDeNegocio(422, "Hay un producto repetido: sumá las unidades en una sola línea")
    if not dentro_de_montevideo(datos.delivery_lat, datos.delivery_lon):
        raise ErrorDeNegocio(422, "Por ahora solo entregamos en Montevideo")

    ajuste = get_router().ajustar((datos.delivery_lat, datos.delivery_lon))
    if ajuste is not None and ajuste[1] > settings.max_distancia_a_calle_m:   # p. ej. un punto en el río
        raise ErrorDeNegocio(422, "Ese punto no está sobre una calle. Marcá un punto más cerca de una calle.")

    comercio = db.get(Merchant, datos.merchant_id)
    if comercio is None:
        raise ErrorDeNegocio(404, "No encontramos ese comercio")
    if not comercio.is_open:
        raise ErrorDeNegocio(409, "Este comercio está cerrado ahora")

    productos = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    for pid in ids:
        if pid not in productos or productos[pid].merchant_id != comercio.id:
            raise ErrorDeNegocio(422, "Uno de los productos no es de este comercio")
    for producto in productos.values():
        if not producto.is_available:
            raise ErrorDeNegocio(409, f"«{producto.name}» no está disponible ahora")
    return comercio, productos


def crear_pedido(
    db: Session, r: redis.Redis, usuario: User, datos: OrderCreateIn, clave: str | None
) -> tuple[int, dict[str, Any], bool]:
    """Crea el pedido. Devuelve (código, cuerpo, es_repetido).

    Idempotencia: la misma clave con el mismo pedido devuelve el pedido ya creado, sin crear otro.
    El candado (advisory lock) hace que dos pedidos con la misma clave que llegan a la vez
    se atiendan de a uno: el segundo ya encuentra la clave guardada.
    """
    if not clave or len(clave) > 80:
        raise ErrorDeNegocio(422, "Falta la cabecera Idempotency-Key (hasta 80 caracteres)")
    huella = _huella(datos)

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"idem:{usuario.id}:{clave}"},
    )
    previo = db.scalar(
        select(IdempotencyKey).where(IdempotencyKey.user_id == usuario.id, IdempotencyKey.key == clave)
    )
    if previo is not None:
        if previo.request_hash != huella:
            raise ErrorDeNegocio(422, "Esa clave ya se usó con otro pedido")
        return previo.response_status, previo.response_body, True

    limite = f"pedidos:{usuario.id}"
    if bloqueado(r, limite, settings.pedidos_max_por_minuto):
        raise ErrorDeNegocio(429, "Demasiados pedidos seguidos. Esperá un momento")

    comercio, productos = _validar(db, datos)
    subtotal = sum(productos[i.product_id].price_cents * i.quantity for i in datos.items)
    pedido = Order(
        customer_user_id=usuario.id, merchant_id=comercio.id, status="recibido",
        delivery_address=datos.delivery_address,
        delivery_location=WKTElement(f"POINT({datos.delivery_lon} {datos.delivery_lat})", srid=4326),
        subtotal_cents=subtotal, delivery_fee_cents=settings.envio_cents,
        total_cents=subtotal + settings.envio_cents, notes=datos.notes,
    )
    db.add(pedido)
    db.flush()
    db.refresh(pedido)
    for i in datos.items:
        p = productos[i.product_id]
        db.add(OrderItem(
            order_id=pedido.id, product_id=p.id, name_snapshot=p.name,
            unit_price_cents=p.price_cents, quantity=i.quantity,
        ))
    db.add(OrderEvent(order_id=pedido.id, from_status=None, to_status="recibido", actor_user_id=usuario.id))
    db.flush()

    cuerpo = jsonable_encoder(detalle_pedido(db, pedido))
    db.add(IdempotencyKey(
        user_id=usuario.id, key=clave, request_hash=huella, response_status=201, response_body=cuerpo,
    ))
    db.commit()
    registrar_fallo(r, limite, settings.pedidos_ventana_segundos)  # cuenta un pedido nuevo
    return 201, cuerpo, False
