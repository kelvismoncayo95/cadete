import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ESTADOS = (
    "recibido", "aceptado", "preparando", "listo", "asignado",
    "en_camino", "entregado", "rechazado", "cancelado",
)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('recibido','aceptado','preparando','listo','asignado',"
            "'en_camino','entregado','rechazado','cancelado')",
            name="status",
        ),
        CheckConstraint("subtotal_cents > 0", name="subtotal_positive"),
        CheckConstraint("delivery_fee_cents >= 0", name="fee_not_negative"),
        CheckConstraint("total_cents > 0", name="total_positive"),
        Index("ix_orders_status", "status", "created_at"),
        Index("ix_orders_customer", "customer_user_id", "created_at"),
        Index("ix_orders_merchant", "merchant_id", "status"),
        # Un repartidor no puede tener dos pedidos activos a la vez.
        Index(
            "ux_courier_active_order", "courier_id", unique=True,
            postgresql_where=text("status IN ('asignado','en_camino')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("merchants.id"))
    courier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("couriers.id"))
    status: Mapped[str] = mapped_column(String(12))
    delivery_address: Mapped[str] = mapped_column(String(160))
    delivery_location = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger)
    delivery_fee_cents: Mapped[int] = mapped_column(BigInteger)
    total_cents: Mapped[int] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("unit_price_cents > 0", name="price_positive"),
        CheckConstraint("quantity BETWEEN 1 AND 20", name="quantity_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    name_snapshot: Mapped[str] = mapped_column(String(80))
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_events_order_id", "order_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    from_status: Mapped[str | None] = mapped_column(String(12))
    to_status: Mapped[str] = mapped_column(String(12))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
