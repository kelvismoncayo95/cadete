import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DispatchOffer(Base):
    __tablename__ = "dispatch_offers"
    __table_args__ = (
        CheckConstraint("status IN ('pendiente','aceptada','rechazada','expirada')", name="status"),
        Index("ix_dispatch_offers_order_id", "order_id", "offered_at"),
        # Una sola oferta pendiente por pedido y por repartidor.
        Index("ux_offer_pending_order", "order_id", unique=True,
              postgresql_where=text("status = 'pendiente'")),
        Index("ux_offer_pending_courier", "courier_id", unique=True,
              postgresql_where=text("status = 'pendiente'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    courier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("couriers.id"))
    status: Mapped[str] = mapped_column(String(10))
    distance_m: Mapped[int | None] = mapped_column(Integer)
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
