import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (Index("ix_merchants_location", "location", postgresql_using="gist"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(30))
    address: Mapped[str] = mapped_column(String(160))
    location = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price_cents > 0", name="price_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("merchants.id"))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(String(200))
    price_cents: Mapped[int] = mapped_column(BigInteger)
    is_available: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
