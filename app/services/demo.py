"""Pedidos de juguete para la demo: los crea el botón «Simular un pedido» y el simulador."""
import random
import uuid

import redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.zone import dentro_de_montevideo
from app.models import Merchant, Product, User
from app.schemas.order import ItemIn, OrderCreateIn
from app.services.errors import ErrorDeNegocio
from app.services.geo import mover_hacia
from app.services.orders import crear_pedido

# Los pedidos simulados se reconocen por esta marca en las notas: el simulador SOLO atiende esos,
# así no se mete con los pedidos de una persona que esté probando la demo.
MARCA = "[simulado]"


def _punto_cerca(rng: random.Random, lat: float, lon: float) -> tuple[float, float]:
    """Un destino a 0,8 a 2,5 km del comercio, dentro de Montevideo (recta, sin calles)."""
    for _ in range(20):
        angulo = rng.uniform(0, 360)
        metros = rng.uniform(800, 2500)
        # un grado de latitud ≈ 111,2 km; el de longitud se achica con el coseno de la latitud
        import math

        dlat = metros * math.cos(math.radians(angulo)) / 111_200
        dlon = metros * math.sin(math.radians(angulo)) / (111_200 * math.cos(math.radians(lat)))
        candidato = (lat + dlat, lon + dlon)
        if dentro_de_montevideo(*candidato):
            return candidato
    return mover_hacia(lat, lon, lat + 0.01, lon, 800)


def crear_pedido_simulado(db: Session, r: redis.Redis, usuario: User, rng: random.Random) -> dict:
    """Crea un pedido de juguete (con la marca de simulado) para ese cliente. Devuelve el cuerpo."""
    comercios = db.execute(text(
        "SELECT id, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon "
        "FROM merchants WHERE is_open ORDER BY id"
    )).all()
    if not comercios:
        raise ErrorDeNegocio(409, "No hay comercios abiertos para simular un pedido")
    comercio = rng.choice(comercios)
    productos = db.scalars(
        select(Product).where(Product.merchant_id == comercio.id, Product.is_available.is_(True)).order_by(Product.id)
    ).all()
    if not productos:
        raise ErrorDeNegocio(409, "Ese comercio no tiene productos disponibles")
    elegidos = rng.sample(productos, k=rng.randint(1, min(3, len(productos))))
    lat, lon = _punto_cerca(rng, comercio.lat, comercio.lon)
    datos = OrderCreateIn(
        merchant_id=comercio.id,
        items=[ItemIn(product_id=p.id, quantity=rng.randint(1, 2)) for p in elegidos],
        delivery_address="Dirección de prueba (demo)",
        delivery_lat=lat,
        delivery_lon=lon,
        notes=MARCA,
    )
    _, cuerpo, _ = crear_pedido(db, r, usuario, datos, f"sim-{uuid.uuid4()}")
    return cuerpo
