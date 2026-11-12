import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis
from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Courier, CourierPosition, Merchant

RADIO_DE_BUSQUEDA_M = 5000  # 5 km (PRD, reglas de negocio)
VIGENCIA_POSICION_REDIS_S = 120
DIAS_DE_HISTORIAL = 7


@dataclass
class Candidato:
    courier: Courier
    distancia_m: float


def buscar_repartidor_mas_cercano(
    db: Session,
    merchant_id: uuid.UUID,
    radio_m: int = RADIO_DE_BUSQUEDA_M,
    excluir: list[uuid.UUID] | None = None,
) -> Candidato | None:
    """El repartidor disponible más cercano al comercio, dentro del radio.

    Lo bloquea (FOR UPDATE SKIP LOCKED): si otro pedido ya lo está eligiendo en este momento,
    se saltea y se devuelve el siguiente más cercano, así dos pedidos nunca reciben al mismo.
    El bloqueo dura hasta el commit o rollback de la sesión que llama.
    """
    distancia = func.ST_Distance(Courier.last_location, Merchant.location)  # en metros (geography)
    consulta = (
        select(Courier, distancia.label("distancia_m"))
        .join(Merchant, Merchant.id == merchant_id)
        .where(
            Courier.status == "available",
            Courier.last_location.is_not(None),
            func.ST_DWithin(Courier.last_location, Merchant.location, radio_m),
        )
        .order_by(distancia, Courier.id)
        .limit(1)
        .with_for_update(of=Courier, skip_locked=True)
    )
    if excluir:
        consulta = consulta.where(Courier.id.not_in(excluir))
    fila = db.execute(consulta).first()
    return Candidato(courier=fila.Courier, distancia_m=fila.distancia_m) if fila else None


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
