import random
import uuid

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import Courier, Merchant, User
from app.schemas.order import OrderDetailOut
from app.seed import DEMO_PASSWORD, usuarios_de_demo
from app.simulator.engine import CLIENTES_DE_LA_DEMO
from app.services.demo import MARCA, MARCA_DEMO, crear_pedido_simulado
from app.services.errors import ErrorDeNegocio
from app.services.events import publicar_estado

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/simulate-order", status_code=201, response_model=OrderDetailOut)
def simular_un_pedido(
    usuario: User = Depends(requiere_rol("customer", "merchant", "courier", "admin")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """El botón «Simular un pedido»: cada rol lo usa para probar SU parte de la demo.

    - cliente: un pedido propio a un comercio al azar (el simulador hace de comercio y de repartidor);
    - comercio: llega un pedido de un cliente de demo a SU comercio, para atenderlo a mano desde el tablero;
    - repartidor: se crea un pedido en el comercio más cercano a su posición (prioridad para él);
    - administrador: un pedido simulado al azar.
    """
    rng = random.Random()
    comercio_id, marca, cliente = None, MARCA, usuario
    if usuario.role != "customer":
        cliente = db.scalar(select(User).where(User.username.in_(CLIENTES_DE_LA_DEMO)).order_by(func.random()).limit(1))
        if cliente is None:
            raise ErrorDeNegocio(409, "No hay clientes de demo: falta sembrar los datos")
    if usuario.role == "merchant":
        comercio_id = db.scalar(select(Merchant.id).where(Merchant.user_id == usuario.id))
        marca = MARCA_DEMO   # lo atiende la persona, no el simulador
    elif usuario.role == "courier":
        comercio_id = db.scalar(
            select(Merchant.id).join(Courier, Courier.user_id == usuario.id)
            .where(Courier.last_location.is_not(None))
            .order_by(func.ST_Distance(Merchant.location, Courier.last_location)).limit(1)
        )
        if comercio_id is None:
            raise ErrorDeNegocio(409, "Primero tocá el mapa para indicar dónde estás")
    cuerpo = crear_pedido_simulado(db, r, cliente, rng, comercio_id=comercio_id, marca=marca)
    publicar_estado(db, r, uuid.UUID(cuerpo["id"]))
    return cuerpo


@router.get("/users")
def usuarios_de_la_demo():
    """Pública a propósito: la contraseña de la demo es única y pública, y solo protege datos inventados."""
    return {"password": DEMO_PASSWORD, "users": usuarios_de_demo()}
