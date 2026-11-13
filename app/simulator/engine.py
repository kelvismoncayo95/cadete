"""Simulador de la demo: le da vida al mapa.

En cada vuelta (tick):
  - los repartidores de la demo se ponen disponibles y se pasean por Montevideo;
  - responden las ofertas (casi siempre aceptan, a veces rechazan o se dejan vencer);
  - con un pedido asignado, van al comercio, lo retiran, van al cliente y lo entregan;
  - un «comercio» acepta, prepara y marca listos los pedidos con la marca [simulado];
  - si no hay ningún pedido simulado activo, crea uno de juguete.

Se mueven POR LAS CALLES: en cada vuelta se pide la ruta al motor (OSRM, que respeta sentidos únicos) y
se avanza esa distancia por la polilínea, doblando en las esquinas. Las decisiones al azar salen de una
semilla fija por oferta/pedido/vuelta, así el simulador es predecible y se puede probar.
"""
import math
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Courier, DispatchOffer, Merchant, Order, OrderEvent, User
from app.seed import SIMULADOS
from app.services.couriers import actualizar_posicion
from app.services.demo import DESTINOS, MARCA, crear_pedido_simulado
from app.services.dispatch import despachar_pedido, responder_oferta
from app.services.entrega import entregar, llegar_al_comercio, retirar
from app.services.errors import ErrorDeNegocio
from app.services.events import EN_CURSO, TERMINALES, publicar_estado, publicar_posicion
from app.services.geo import distancia_m, punto_a_distancia
from app.services.order_state import cambiar_estado
from app.services.routing import get_router

REPARTIDORES_DE_LA_DEMO = SIMULADOS
CLIENTES_DE_LA_DEMO = ("ana", "pedro")
PASEO_CADA_S = 90                # cada tanto el repartidor libre elige otro punto al que ir
SIGUIENTE_DEL_COMERCIO = {"recibido": "aceptado", "aceptado": "preparando", "preparando": "listo"}


@dataclass
class Config:
    velocidad_ms: float = 25.0           # metros por segundo (rápido a propósito: es una demo)
    tick_s: int = 5
    prob_aceptar: float = 0.8
    prob_rechazar: float = 0.1           # el resto de las veces se deja vencer
    demora_oferta_s: tuple[float, float] = (3.0, 8.0)
    demora_comercio_s: tuple[float, float] = (4.0, 8.0)
    generar_pedidos: bool = True
    llegada_m: float = 40.0              # a esta distancia se considera que llegó


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _coords(db: Session, columna: str, tabla: str, id_) -> tuple[float, float]:
    fila = db.execute(
        text(f"SELECT ST_Y({columna}::geometry), ST_X({columna}::geometry) FROM {tabla} WHERE id = :id"), {"id": id_}
    ).one()
    return fila[0], fila[1]


def _mover_por_ruta(db, r, rep: Courier, destino: tuple[float, float], metros: float) -> tuple[float, float, bool]:
    """Avanza `metros` por la ruta de calles hasta el destino. Devuelve (lat, lon, llegó)."""
    lat, lon = _coords(db, "last_location", "couriers", rep.id)
    ruta = get_router().ruta([(lat, lon), destino])
    nlat, nlon, llego = punto_a_distancia(ruta.coordenadas, metros)
    actualizar_posicion(db, r, rep, nlat, nlon)
    publicar_posicion(db, r, rep, nlat, nlon)
    return nlat, nlon, llego


def _repartidores(db: Session) -> list[Courier]:
    return list(db.scalars(
        select(Courier).join(User, User.id == Courier.user_id)
        .where(User.username.in_(REPARTIDORES_DE_LA_DEMO)).order_by(User.username)
    ))


def _bases(db: Session) -> list[tuple[float, float]]:
    """Puntos en TIERRA FIRME entre los que se mueven los repartidores libres: los comercios y los barrios
    de la lista de destinos (verificados con `map/verificar_destinos.py`)."""
    comercios = db.execute(text("SELECT ST_Y(location::geometry), ST_X(location::geometry) FROM merchants ORDER BY id")).all()
    return [(d[1], d[2]) for d in DESTINOS] + [(c[0], c[1]) for c in comercios]


def _inicializar(db, r, rep: Courier, rng: random.Random) -> None:
    """Primera vez: aparece sobre una calle cerca de algún punto conocido y queda disponible."""
    lat, lon = rng.choice(_bases(db))
    lat, lon = lat + rng.uniform(-0.0004, 0.0004), lon + rng.uniform(-0.0004, 0.0004)
    ajuste = get_router().ajustar((lat, lon))
    if ajuste is not None:
        lat, lon = ajuste[0]   # encima de la calle más cercana
    actualizar_posicion(db, r, rep, lat, lon)
    publicar_posicion(db, r, rep, lat, lon)


def _pasear(db, r, rep: Courier, ahora: datetime, cfg: Config) -> None:
    """El repartidor libre recorre la ciudad: va por las calles hacia un punto conocido y, cada 90 s,
    elige otro. El destino sale de una semilla (repartidor + franja de tiempo): es estable y probable."""
    azar = random.Random(f"{rep.id}:{int(ahora.timestamp() // PASEO_CADA_S)}")
    destino = azar.choice(_bases(db))
    _mover_por_ruta(db, r, rep, destino, cfg.velocidad_ms * cfg.tick_s * 0.5)


def _responder_ofertas(db, r, rep: Courier, ahora: datetime, cfg: Config) -> int:
    hechas = 0
    ofertas = db.scalars(
        select(DispatchOffer).where(DispatchOffer.courier_id == rep.id, DispatchOffer.status == "pendiente")
    ).all()
    for oferta in ofertas:
        azar = random.Random(str(oferta.id))  # la decisión de esta oferta es siempre la misma
        espera = azar.uniform(*cfg.demora_oferta_s)
        if ahora < oferta.offered_at + timedelta(seconds=espera):
            continue
        suerte = azar.random()
        if suerte < cfg.prob_aceptar:
            aceptar = True
        elif suerte < cfg.prob_aceptar + cfg.prob_rechazar:
            aceptar = False
        else:
            continue  # se la deja vencer
        try:
            responder_oferta(db, oferta.id, rep.user_id, aceptar=aceptar, ahora=ahora)
        except ErrorDeNegocio:
            db.rollback()
            continue
        publicar_estado(db, r, oferta.order_id)
        hechas += 1
    return hechas


def _avanzar_entrega(db, r, rep: Courier, cfg: Config) -> int:
    """Un repartidor simulado hace lo mismo que una persona: va al comercio, marca la llegada, retira,
    va al cliente y entrega. Cada paso exige estar cerca (lo comprueba el servidor)."""
    pedido = db.scalar(select(Order).where(Order.courier_id == rep.id, Order.status.in_(EN_CURSO)))
    if pedido is None:
        return 0
    if pedido.status == "en_comercio":
        retirar(db, pedido, rep.user_id)
        db.commit()
        publicar_estado(db, r, pedido.id)
        return 1
    if pedido.status == "asignado":
        destino = _coords(db, "location", "merchants", pedido.merchant_id)
    else:
        destino = _coords(db, "delivery_location", "orders", pedido.id)
    lat, lon, llego = _mover_por_ruta(db, r, rep, destino, cfg.velocidad_ms * cfg.tick_s)
    if not llego and distancia_m(lat, lon, *destino) > cfg.llegada_m:
        return 0
    try:
        (llegar_al_comercio if pedido.status == "asignado" else entregar)(db, pedido, rep.user_id)
    except ErrorDeNegocio:
        db.rollback()   # todavía no está lo bastante cerca: reintenta en la próxima vuelta
        return 0
    db.commit()
    publicar_estado(db, r, pedido.id)
    return 1


def _conducir_humanos(db, r, cfg: Config) -> int:
    """Piloto automático (demo): conduce la moto de un repartidor HUMANO por las calles hacia su próximo
    destino. Solo la mueve: llegar, retirar y entregar los marca la persona con los botones."""
    movidos = 0
    for clave in r.scan_iter("autopilot:*"):
        rep = db.get(Courier, uuid.UUID(clave.split(":", 1)[1]))
        if rep is None or rep.status != "busy":
            continue
        pedido = db.scalar(select(Order).where(Order.courier_id == rep.id, Order.status.in_(("asignado", "en_camino"))))
        if pedido is None:
            continue   # en el comercio esperando que la persona marque «Retiré»: no se mueve
        if pedido.status == "asignado":
            destino = _coords(db, "location", "merchants", pedido.merchant_id)
        else:
            destino = _coords(db, "delivery_location", "orders", pedido.id)
        _mover_por_ruta(db, r, rep, destino, cfg.velocidad_ms * cfg.tick_s)
        movidos += 1
    return movidos


def _atender_comercios(db, r, ahora: datetime, cfg: Config) -> int:
    """El «comercio» de la demo: acepta, prepara y marca listos los pedidos simulados."""
    hechos = 0
    pedidos = db.scalars(select(Order).where(Order.notes == MARCA, Order.status.in_(list(SIGUIENTE_DEL_COMERCIO)))).all()
    for pedido in pedidos:
        desde = db.scalar(select(func.max(OrderEvent.created_at)).where(OrderEvent.order_id == pedido.id)) or pedido.created_at
        espera = random.Random(f"{pedido.id}:{pedido.status}").uniform(*cfg.demora_comercio_s)
        if ahora < desde + timedelta(seconds=espera):
            continue
        dueno = db.scalar(select(Merchant.user_id).where(Merchant.id == pedido.merchant_id))
        siguiente = SIGUIENTE_DEL_COMERCIO[pedido.status]
        cambiar_estado(db, pedido.id, siguiente, actor_user_id=dueno)
        if siguiente == "listo":
            db.flush()
            despachar_pedido(db, pedido.id, ahora)
        db.commit()
        publicar_estado(db, r, pedido.id)
        hechos += 1
    return hechos


def _generar_pedido(db, r, rng: random.Random) -> int:
    activos = db.scalar(
        select(func.count()).select_from(Order).where(Order.notes == MARCA, Order.status.not_in(TERMINALES))
    )
    if activos:
        return 0
    cliente = db.scalar(select(User).where(User.username == rng.choice(CLIENTES_DE_LA_DEMO)))
    if cliente is None:
        return 0
    try:
        cuerpo = crear_pedido_simulado(db, r, cliente, rng)
    except ErrorDeNegocio:
        db.rollback()
        return 0
    import uuid

    publicar_estado(db, r, uuid.UUID(cuerpo["id"]))
    return 1


def tick(db: Session, r: redis.Redis, ahora: datetime | None = None, cfg: Config | None = None,
         rng: random.Random | None = None) -> dict[str, int]:
    ahora = ahora or _ahora()
    cfg = cfg or Config()
    rng = rng or random.Random()
    resumen = {"ofertas": 0, "entregas": 0, "comercio": 0, "pedidos": 0, "piloto": 0}
    for rep in _repartidores(db):
        if rep.last_location is None:
            _inicializar(db, r, rep, rng)
            if rep.status == "offline":
                rep.status = "available"
                db.commit()
            continue
        if rep.status == "available":
            respondidas = _responder_ofertas(db, r, rep, ahora, cfg)
            resumen["ofertas"] += respondidas
            if respondidas:
                continue  # una cosa por vuelta: responde ahora y se mueve en la próxima
            db.refresh(rep)
        if rep.status == "available":
            _pasear(db, r, rep, ahora, cfg)
        elif rep.status == "busy":
            resumen["entregas"] += _avanzar_entrega(db, r, rep, cfg)
    resumen["piloto"] = _conducir_humanos(db, r, cfg)
    resumen["comercio"] = _atender_comercios(db, r, ahora, cfg)
    if cfg.generar_pedidos:
        resumen["pedidos"] = _generar_pedido(db, r, rng)
    return resumen
