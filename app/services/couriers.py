import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis
from geoalchemy2 import Geometry
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, delete, exists, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Courier, CourierPosition, DispatchOffer, Merchant, User
from app.services.routing import get_router

RADIO_DE_BUSQUEDA_M = 5000  # 5 km (PRD, reglas de negocio)
VIGENCIA_POSICION_REDIS_S = 120
DIAS_DE_HISTORIAL = 7


@dataclass
class Candidato:
    courier: Courier
    distancia_m: float


CANDIDATOS_A_EVALUAR = 8   # los más cercanos en línea recta; entre ellos se elige el más rápido POR CALLE


def buscar_repartidor_mas_cercano(
    db: Session,
    merchant_id: uuid.UUID,
    radio_m: int = RADIO_DE_BUSQUEDA_M,
    excluir: list[uuid.UUID] | None = None,
    excluir_usuarios: set[str] | None = None,
) -> Candidato | None:
    """El repartidor disponible que llega MÁS RÁPIDO al comercio por las calles, dentro del radio.

    1) Se arma una lista corta con los más cercanos en línea recta (barato, usa el índice espacial).
    2) El motor de rutas calcula el tiempo real por calle de cada uno (respeta sentidos únicos).
    3) Se intenta bloquear al mejor (FOR UPDATE SKIP LOCKED): si otro pedido ya lo está tomando, se
       pasa al siguiente mejor. Así dos pedidos nunca reciben al mismo repartidor.
    El bloqueo dura hasta el commit o rollback de la sesión que llama.
    """
    comercio = db.execute(
        select(func.ST_Y(cast(Merchant.location, Geometry)), func.ST_X(cast(Merchant.location, Geometry)))
        .where(Merchant.id == merchant_id)
    ).first()
    if comercio is None:
        return None
    geometria = cast(Courier.last_location, Geometry)
    en_recta = func.ST_Distance(Courier.last_location, select(Merchant.location).where(Merchant.id == merchant_id).scalar_subquery())
    lista = (
        select(Courier.id, func.ST_Y(geometria), func.ST_X(geometria), User.username)
        .join(User, User.id == Courier.user_id)
        .where(
            Courier.status == "available",
            Courier.last_location.is_not(None),
            ~exists().where(DispatchOffer.courier_id == Courier.id, DispatchOffer.status == "pendiente"),
            func.ST_DWithin(Courier.last_location, select(Merchant.location).where(Merchant.id == merchant_id).scalar_subquery(), radio_m),
        )
        .order_by(en_recta, Courier.id)
        .limit(CANDIDATOS_A_EVALUAR)
    )
    if excluir:
        lista = lista.where(Courier.id.not_in(excluir))
    if excluir_usuarios:
        lista = lista.where(User.username.not_in(excluir_usuarios))
    candidatos = db.execute(lista).all()
    if not candidatos:
        return None

    tabla = get_router().tabla([(c[1], c[2]) for c in candidatos], (comercio[0], comercio[1])) or []
    prioritarios = settings.prioritarios   # demo: los repartidores «humanos» van primero
    ordenados = sorted(
        ((0 if c[3] in prioritarios else 1, t[0], t[1], c[0]) for c, t in zip(candidatos, tabla) if t is not None),
        key=lambda x: (x[0], x[1], str(x[3])),
    )
    for _prioridad, _segundos, metros, courier_id in ordenados:
        elegido = db.execute(
            select(Courier)
            .where(
                Courier.id == courier_id,
                Courier.status == "available",
                ~exists().where(DispatchOffer.courier_id == Courier.id, DispatchOffer.status == "pendiente"),
            )
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if elegido is not None:
            return Candidato(courier=elegido, distancia_m=metros)
    return None


def actualizar_posicion(db: Session, r: redis.Redis, repartidor: Courier, lat: float, lon: float) -> None:
    """Guarda la posición: la actual (en la base y en Redis) y una más en el historial."""
    punto = WKTElement(f"POINT({lon} {lat})", srid=4326)
    ahora = datetime.now(timezone.utc)
    repartidor.last_location = punto
    repartidor.last_seen_at = ahora
    db.add(CourierPosition(courier_id=repartidor.id, location=punto, recorded_at=ahora))
    db.commit()
    r.set(
        f"courier:{repartidor.id}:pos",
        json.dumps({"lat": lat, "lon": lon, "at": ahora.isoformat()}),
        ex=VIGENCIA_POSICION_REDIS_S,
    )


def purgar_posiciones_antiguas(db: Session, dias: int = DIAS_DE_HISTORIAL) -> int:
    """Borra el historial de posiciones de más de `dias` días. Devuelve cuántas borró."""
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    resultado = db.execute(delete(CourierPosition).where(CourierPosition.recorded_at < limite))
    db.commit()
    return resultado.rowcount
