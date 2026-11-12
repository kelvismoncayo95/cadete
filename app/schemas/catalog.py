import uuid

from pydantic import BaseModel


class MerchantOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    address: str
    lat: float
    lon: float


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price_cents: int
