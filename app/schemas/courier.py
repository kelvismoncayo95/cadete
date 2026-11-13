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
    pay_cents: int        # lo que cobraría el repartidor (incluye el viaje al comercio)
    pickup_m: int | None  # distancia por calle hasta el comercio
    delivery_m: int       # distancia por calle del comercio al cliente
    expires_at: datetime
    seconds_left: int
