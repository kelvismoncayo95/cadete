"""La entrega paso a paso. Cada paso exige estar CERCA del lugar (el servidor lo comprueba; los botones de
la pantalla solo reflejan lo mismo):

  asignado ──llegué al comercio (≤ 25 m)──▶ en_comercio ──retiré──▶ en_camino ──entregué (≤ 25 m del cliente)──▶ entregado
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Courier, Order
from app.services.errors import ErrorDeNegocio
from app.services.events import coordenadas_del_pedido
from app.services.geo import distancia_m
from app.services.order_state import TransicionInvalida, cambiar_estado, puede_pasar
from app.services.pagos import registrar_cobros
from app.services.routing import get_router


def metros_hasta(db: Session, pedido: Order, objetivo: str) -> float | None:
    """Distancia del repartidor al comercio ('comercio') o al cliente ('cliente'); None si no tiene posición.

    Se mide hasta el punto O hasta la calle más cercana a él (un comercio puede quedar adentro de una manzana
    y la moto solo puede llegar a la calle)."""
    c = coordenadas_del_pedido(db, pedido.id)
    if c["clat"] is None:
        return None
    punto = (c["mlat"], c["mlon"]) if objetivo == "comercio" else (c["dlat"], c["dlon"])
    ajuste = get_router().ajustar(punto)
    calle = ajuste[0] if ajuste else punto
    return min(distancia_m(c["clat"], c["clon"], *punto), distancia_m(c["clat"], c["clon"], *calle))


def _exigir_cercania(db: Session, pedido: Order, objetivo: str) -> None:
    metros = metros_hasta(db, pedido, objetivo)
    radio = settings.radio_llegada_m
    if metros is None or metros > radio:
        donde = "del comercio" if objetivo == "comercio" else "del cliente"
        dist = "sin ubicación" if metros is None else f"a {int(round(metros / 10) * 10)} m {donde}"
        accion = "marcar tu llegada" if objetivo == "comercio" else "entregar"
        raise ErrorDeNegocio(409, f"Todavía estás {dist}. Acercate a menos de {int(radio)} m para {accion}.")


def llegar_al_comercio(db: Session, pedido: Order, user_id: uuid.UUID) -> None:
    if not puede_pasar(pedido.status, "en_comercio"):
        raise TransicionInvalida(pedido.status, "en_comercio")
    _exigir_cercania(db, pedido, "comercio")
    cambiar_estado(db, pedido.id, "en_comercio", actor_user_id=user_id)


def retirar(db: Session, pedido: Order, user_id: uuid.UUID) -> None:
    cambiar_estado(db, pedido.id, "en_camino", actor_user_id=user_id)   # solo desde «en_comercio»


def entregar(db: Session, pedido: Order, user_id: uuid.UUID) -> None:
    if not puede_pasar(pedido.status, "entregado"):
        raise TransicionInvalida(pedido.status, "entregado")
    _exigir_cercania(db, pedido, "cliente")
    cambiar_estado(db, pedido.id, "entregado", actor_user_id=user_id)
    repartidor = db.scalar(select(Courier).where(Courier.id == pedido.courier_id))
    repartidor.status = "available"          # queda libre para el próximo pedido
    registrar_cobros(db, pedido)             # se cobra al cliente y se paga al comercio y al repartidor
