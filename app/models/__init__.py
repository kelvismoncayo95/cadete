# Importar todos los modelos acá hace que Alembic los vea.
from app.models.base import Base
from app.models.courier import Courier, CourierPosition
from app.models.dispatch import DispatchOffer
from app.models.merchant import Merchant, Product
from app.models.order import Order, OrderEvent, OrderItem
from app.models.system import AuditLog, IdempotencyKey
from app.models.user import User

__all__ = [
    "AuditLog", "Base", "Courier", "CourierPosition", "DispatchOffer", "IdempotencyKey",
    "Merchant", "Order", "OrderEvent", "OrderItem", "Product", "User",
]
