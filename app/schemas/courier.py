import uuid
from datetime import datetime

from pydantic import BaseModel


class OfertaOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    merchant_name: str
    merchant_address: str
    delivery_address: str
    distance_m: int | None
    fee_cents: int
    expires_at: datetime
    seconds_left: int
