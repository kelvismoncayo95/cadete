"""Quién puede ver qué pedidos. Una sola regla, usada por todos los endpoints."""
from sqlalchemy import Select, select

from app.models import Courier, Merchant, Order, User


def pedidos_visibles(usuario: User) -> Select:
    """Consulta de pedidos que ESTE usuario tiene derecho a ver.

    Lo que queda fuera de la consulta no existe para él: se responde 404, no 403,
    para no revelar que ese pedido existe.
    """
    consulta = select(Order)
    if usuario.role == "admin":
        return consulta
    if usuario.role == "customer":
        return consulta.where(Order.customer_user_id == usuario.id)
    if usuario.role == "merchant":
        return consulta.where(
            Order.merchant_id.in_(select(Merchant.id).where(Merchant.user_id == usuario.id))
        )
    if usuario.role == "courier":
        return consulta.where(
            Order.courier_id.in_(select(Courier.id).where(Courier.user_id == usuario.id))
        )
    return consulta.where(False)
