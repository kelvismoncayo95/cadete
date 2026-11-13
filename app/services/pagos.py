"""Pagos de juguete: cuánto cobra el repartidor y los asientos del libro de movimientos.

Cada pedido ENTREGADO deja cuatro asientos que suman cero:
  cliente −total · comercio +90 % de los productos · repartidor +su pago · plataforma +lo que sobra (o falta).
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Courier, LedgerEntry, Merchant, Order

MONTEVIDEO = ZoneInfo("America/Montevideo")


def calcular_pago_repartidor(distancia_retiro_m: float, distancia_entrega_m: float) -> int:
    """Base + un monto por km, contando el viaje hasta el comercio Y el de la entrega. Al peso más cercano.

    (Antes solo se cobraba un envío fijo: ir hasta la tienda no se pagaba.)"""
    km = (distancia_retiro_m + distancia_entrega_m) / 1000
    bruto = settings.pago_base_repartidor_cents + km * settings.pago_por_km_repartidor_cents
    return int(round(bruto / 100) * 100)


def registrar_cobros(db: Session, pedido: Order) -> None:
    """Cobra al cliente y paga al comercio y al repartidor. Se puede llamar una sola vez por pedido."""
    ya_hecho = db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.order_id == pedido.id))
    if ya_hecho:
        return
    comercio_user = db.scalar(select(Merchant.user_id).where(Merchant.id == pedido.merchant_id))
    repartidor_user = db.scalar(select(Courier.user_id).where(Courier.id == pedido.courier_id))
    para_comercio = pedido.subtotal_cents * (100 - settings.comision_comercio_pct) // 100
    para_repartidor = pedido.courier_pay_cents or 0
    plataforma = pedido.total_cents - para_comercio - para_repartidor   # puede ser negativa: la plataforma subsidia
    db.add_all([
        LedgerEntry(order_id=pedido.id, user_id=pedido.customer_user_id, concept="cobro_cliente", amount_cents=-pedido.total_cents),
        LedgerEntry(order_id=pedido.id, user_id=comercio_user, concept="pago_comercio", amount_cents=para_comercio),
        LedgerEntry(order_id=pedido.id, user_id=repartidor_user, concept="pago_repartidor", amount_cents=para_repartidor),
        LedgerEntry(order_id=pedido.id, user_id=None, concept="plataforma", amount_cents=plataforma),
    ])
    db.flush()


def saldo(db: Session, user_id) -> dict:
    """Saldo total, lo de hoy (desde medianoche de Montevideo) y los últimos movimientos."""
    medianoche = datetime.combine(datetime.now(MONTEVIDEO).date(), time.min, MONTEVIDEO).astimezone(timezone.utc)
    total = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(LedgerEntry.user_id == user_id))
    hoy = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
        LedgerEntry.user_id == user_id, LedgerEntry.created_at >= medianoche))
    movimientos = db.scalars(
        select(LedgerEntry).where(LedgerEntry.user_id == user_id).order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc()).limit(20)
    ).all()
    return {
        "balance_cents": int(total), "today_cents": int(hoy),
        "movements": [{"order_id": str(m.order_id), "concept": m.concept, "amount_cents": m.amount_cents,
                       "at": m.created_at.isoformat()} for m in movimientos],
    }
