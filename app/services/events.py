"""Eventos en vivo: se publican en Redis (pub/sub) y los streams SSE los reenvían al navegador.

Cada pedido tiene su canal; hay además un canal general para el mapa del administrador.
Los eventos son AUTOSUFICIENTES (llevan todo lo que el cliente necesita), así el stream
no necesita consultar la base mientras está abierto.
"""
import json
import math
import uuid
from typing import Any

import redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Courier, Order
from app.services.routing import get_router

CANAL_TODO = "live:all"
TERMINALES = ("entregado", "rechazado", "cancelado")
EN_CURSO = ("asignado", "en_camino")


def canal_pedido(order_id: uuid.UUID | str) -> str:
    return f"order:{order_id}"


def _coordenadas(db: Session, order_id: uuid.UUID) -> dict[str, Any]:
    fila = db.execute(
        text(
            "SELECT ST_Y(m.location::geometry) AS mlat, ST_X(m.location::geometry) AS mlon, "
            "ST_Y(o.delivery_location::geometry) AS dlat, ST_X(o.delivery_location::geometry) AS dlon, "
            "ST_Y(c.last_location::geometry) AS clat, ST_X(c.last_location::geometry) AS clon "
            "FROM orders o JOIN merchants m ON m.id = o.merchant_id "
            "LEFT JOIN couriers c ON c.id = o.courier_id WHERE o.id = :id"
        ),
        {"id": order_id},
    ).one()
    return dict(fila._mapping)


def ruta_del_pedido(estado: str, courier: tuple[float, float] | None, comercio: tuple[float, float],
                    destino: tuple[float, float]):
    """La ruta por calles que se dibuja: repartidor → comercio → cliente (asignado), repartidor → cliente
    (en camino) o comercio → cliente (todavía sin repartidor)."""
    if courier and estado == "asignado":
        puntos = [courier, comercio, destino]
    elif courier and estado == "en_camino":
        puntos = [courier, destino]
    else:
        puntos = [comercio, destino]
    return get_router().ruta(puntos)


def eta_minutos(estado: str, courier, ruta) -> int | None:
    """Minutos que faltan, según la duración de la ruta (solo con un pedido en curso)."""
    if courier is None or estado not in EN_CURSO or ruta is None:
        return None
    return math.ceil(ruta.duracion_s / settings.aceleracion_demo / 60)


def _coordenadas_de_ruta(ruta) -> list[list[float]]:
    return [[lon, lat] for lat, lon in ruta.coordenadas]   # GeoJSON: [lon, lat]


def datos_de_pedido(db: Session, pedido: Order) -> dict[str, Any]:
    c = _coordenadas(db, pedido.id)
    courier = (c["clat"], c["clon"]) if c["clat"] is not None else None
    comercio, destino = (c["mlat"], c["mlon"]), (c["dlat"], c["dlon"])
    ruta = ruta_del_pedido(pedido.status, courier, comercio, destino)
    return {
        "tipo": "estado",
        "order_id": str(pedido.id),
        "status": pedido.status,
        "eta_min": eta_minutos(pedido.status, courier, ruta),
        "courier": {"lat": courier[0], "lon": courier[1]} if courier else None,
        "merchant": {"lat": comercio[0], "lon": comercio[1]},
        "destino": {"lat": destino[0], "lon": destino[1]},
        "route": _coordenadas_de_ruta(ruta),
    }


def _publicar(r: redis.Redis, canales: list[str], datos: dict[str, Any]) -> None:
    mensaje = json.dumps(datos)
    for canal in canales:
        r.publish(canal, mensaje)


def publicar_estado(db: Session, r: redis.Redis, order_id: uuid.UUID) -> None:
    """Llamar DESPUÉS del commit: avisa el estado actual del pedido."""
    pedido = db.get(Order, order_id)
    db.refresh(pedido)
    _publicar(r, [canal_pedido(order_id), CANAL_TODO], datos_de_pedido(db, pedido))


def publicar_posicion(db: Session, r: redis.Redis, repartidor: Courier, lat: float, lon: float) -> None:
    """Llamar DESPUÉS de guardar la posición. Avisa al mapa general y, si tiene un pedido en curso, a ese pedido."""
    _publicar(r, [CANAL_TODO], {
        "tipo": "repartidor", "courier_id": str(repartidor.id), "lat": lat, "lon": lon, "status": repartidor.status,
    })
    pedido = db.scalar(select(Order).where(Order.courier_id == repartidor.id, Order.status.in_(EN_CURSO)))
    if pedido is None:
        return
    c = _coordenadas(db, pedido.id)
    ruta = ruta_del_pedido(pedido.status, (lat, lon), (c["mlat"], c["mlon"]), (c["dlat"], c["dlon"]))
    _publicar(r, [canal_pedido(pedido.id)], {
        "tipo": "posicion", "order_id": str(pedido.id), "lat": lat, "lon": lon,
        "eta_min": eta_minutos(pedido.status, (lat, lon), ruta), "route": _coordenadas_de_ruta(ruta),
    })


def datos_admin(db: Session) -> dict[str, Any]:
    """Foto inicial del mapa del administrador: repartidores con posición y pedidos activos."""
    repartidores = db.execute(text(
        "SELECT id::text AS id, status, ST_Y(last_location::geometry) AS lat, ST_X(last_location::geometry) AS lon "
        "FROM couriers WHERE last_location IS NOT NULL ORDER BY id"
    )).mappings().all()
    pedidos = db.scalars(select(Order).where(Order.status.not_in(TERMINALES)).order_by(Order.created_at)).all()
    return {
        "tipo": "snapshot",
        "couriers": [dict(f) for f in repartidores],
        "orders": [datos_de_pedido(db, p) for p in pedidos],
    }
