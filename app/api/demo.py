import random
import uuid

import redis
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import User
from app.schemas.order import OrderDetailOut
from app.services.demo import crear_pedido_simulado
from app.services.events import publicar_estado

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/simulate-order", status_code=201, response_model=OrderDetailOut)
def simular_un_pedido(
    usuario: User = Depends(requiere_rol("customer")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """El botón «Simular un pedido»: crea un pedido de juguete para este cliente.

    El simulador lo atiende solo (el comercio lo prepara y un repartidor lo lleva).
    """
    cuerpo = crear_pedido_simulado(db, r, usuario, random.Random())
    publicar_estado(db, r, uuid.UUID(cuerpo["id"]))
    return cuerpo
