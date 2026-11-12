from typing import Literal

import redis
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import Courier, User
from app.services.couriers import actualizar_posicion
from app.services.errors import ErrorDeNegocio

router = APIRouter(prefix="/courier", tags=["repartidor"])


class PosicionIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class EstadoIn(BaseModel):
    status: Literal["available", "offline"]


def _mi_repartidor(db: Session, usuario: User) -> Courier:
    repartidor = db.scalar(select(Courier).where(Courier.user_id == usuario.id))
    if repartidor is None:
        raise HTTPException(404, "No encontramos tu perfil de repartidor")
    return repartidor


@router.post("/location", status_code=204)
def enviar_posicion(
    datos: PosicionIn,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> Response:
    actualizar_posicion(db, r, _mi_repartidor(db, usuario), datos.lat, datos.lon)
    return Response(status_code=204)


@router.post("/status")
def cambiar_estado_del_repartidor(
    datos: EstadoIn,
    usuario: User = Depends(requiere_rol("courier")),
    db: Session = Depends(get_db),
):
    repartidor = _mi_repartidor(db, usuario)
    if repartidor.status == "busy":
        raise ErrorDeNegocio(409, "Tenés un pedido en curso: terminá la entrega primero")
    repartidor.status = datos.status
    db.commit()
    return {"status": repartidor.status}
