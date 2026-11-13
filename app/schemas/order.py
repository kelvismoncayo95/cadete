import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int  # el rango (1 a 20) lo valida el servicio, con un mensaje claro


class OrderCreateIn(BaseModel):
    merchant_id: uuid.UUID
    items: list[ItemIn] = []
    delivery_address: str = Field(min_length=1, max_length=160)
    delivery_lat: float
    delivery_lon: float
    notes: str | None = Field(default=None, max_length=200)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    merchant_id: uuid.UUID
    courier_id: uuid.UUID | None
    delivery_address: str
    subtotal_cents: int
    delivery_fee_cents: int
    total_cents: int
    courier_pay_cents: int | None = None
    created_at: datetime


class ItemOut(BaseModel):
    name: str
    unit_price_cents: int
    quantity: int


class OrderDetailOut(OrderOut):
    items: list[ItemOut]


class RechazoIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)
