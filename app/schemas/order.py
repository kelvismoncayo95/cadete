import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    created_at: datetime
