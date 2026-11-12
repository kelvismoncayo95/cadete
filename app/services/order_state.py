"""Máquina de estados del pedido: el ÚNICO lugar donde se decide qué cambios son válidos."""
import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Order, OrderEvent

# estado actual -> estados a los que puede pasar
TRANSICIONES: dict[str, frozenset[str]] = {
    "recibido": frozenset({"aceptado", "rechazado", "cancelado"}),
    "aceptado": frozenset({"preparando", "cancelado"}),
    "preparando": frozenset({"listo", "cancelado"}),
    "listo": frozenset({"asignado"}),
    "asignado": frozenset({"en_camino"}),
    "en_camino": frozenset({"entregado"}),
    "entregado": frozenset(),
    "rechazado": frozenset(),
    "cancelado": frozenset(),
}


class TransicionInvalida(Exception):
    def __init__(self, actual: str, destino: str):
        self.actual = actual
        self.destino = destino
        super().__init__(f"No se puede pasar de «{actual}» a «{destino}»")


class OrderNotFound(Exception):
    pass


def puede_pasar(origen: str, destino: str) -> bool:
    return destino in TRANSICIONES.get(origen, frozenset())


def cambiar_estado(
    session: Session,
    order_id: uuid.UUID,
    destino: str,
    actor_user_id: uuid.UUID | None = None,
    detalle: dict[str, Any] | None = None,
) -> Order:
    """Cambia el estado del pedido y deja una fila en order_events.

    Bloquea la fila del pedido (FOR UPDATE) hasta el commit: si dos personas intentan
    cambiarlo a la vez, la segunda espera y después ve el estado ya cambiado.
    No hace commit: lo hace quien llama, para que todo ocurra en una sola transacción.
    """
    pedido = session.get(Order, order_id, with_for_update=True)
    if pedido is None:
        raise OrderNotFound(str(order_id))
    if not puede_pasar(pedido.status, destino):
        raise TransicionInvalida(pedido.status, destino)

    session.add(
        OrderEvent(
            order_id=pedido.id,
            from_status=pedido.status,
            to_status=destino,
            actor_user_id=actor_user_id,
            detail=detalle,
        )
    )
    pedido.status = destino
    pedido.updated_at = func.now()
    session.flush()
    return pedido
