import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Courier(Base):
    __tablename__ = "couriers"
    __table_args__ = (
        CheckConstraint("vehicle IN ('moto','bici')", name="vehicle"),
        CheckConstraint("status IN ('offline','available','busy')", name="status"),
        Index("ix_couriers_location", "last_location", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    vehicle: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), server_default="offline")
    last_location = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourierPosition(Base):
    """Histórico de posiciones (se conserva 7 días). La actual vive en Redis."""

    __tablename__ = "courier_positions"
    __table_args__ = (Index("ix_courier_positions_courier_id", "courier_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    courier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("couriers.id"))
    location = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
