import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ROLES = ("customer", "merchant", "courier", "admin")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('customer','merchant','courier','admin')", name="role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    username: Mapped[str] = mapped_column(String(30), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
