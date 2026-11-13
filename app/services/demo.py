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
# Los pedidos de prueba que se le mandan a un comercio llevan ESTA marca: no los toca el simulador,
# los atiende la persona desde el tablero.
MARCA_DEMO = "[demo]"


# Destinos de la demo: puntos en tierra firme de distintos barrios (aproximados). Se eligieron a mano
# porque el rectángulo de la zona de entrega incluye agua (el Río de la Plata) y un pedido no puede
# «entregarse» en el río. Se verificaron mirando el mapa.
DESTINOS = [
    ("Pocitos", -34.9115, -56.1495), ("Buceo", -34.8890, -56.1325), ("Malvín", -34.8923, -56.1070),
    ("Punta Carretas", -34.9235, -56.1585), ("Parque Rodó", -34.9150, -56.1650), ("Cordón", -34.9040, -56.1790),
    ("Centro", -34.9055, -56.1895), ("Ciudad Vieja", -34.9070, -56.2010), ("Tres Cruces", -34.8940, -56.1670),
    ("La Blanqueada", -34.8890, -56.1580), ("Palermo", -34.9110, -56.1850), ("Goes", -34.8870, -56.1790),
    ("Unión", -34.8860, -56.1480), ("Prado", -34.8620, -56.2050), ("Carrasco", -34.8800, -56.0620),
]


def _destino_cerca(rng: random.Random, lat: float, lon: float) -> tuple[str, float, float]:
    """Un destino de la lista, entre 400 m y 5 km del comercio (de los más cercanos, elegido al azar)."""
    from app.services.geo import distancia_m

    candidatos = sorted(
        ((distancia_m(lat, lon, d[1], d[2]), d) for d in DESTINOS), key=lambda par: par[0]
    )
    cerca = [d for metros, d in candidatos if 400 <= metros <= 5000] or [candidatos[-1][1]]
    return rng.choice(cerca[:5])


def crear_pedido_simulado(db: Session, r: redis.Redis, usuario: User, rng: random.Random,
                          comercio_id: uuid.UUID | None = None, marca: str = MARCA) -> dict:
    """Crea un pedido de juguete (con la marca de simulado) para ese cliente. Devuelve el cuerpo."""
    comercios = db.execute(text(
        "SELECT id, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon "
        "FROM merchants WHERE is_open " + ("AND id = :id " if comercio_id else "") + "ORDER BY id"
    ), {"id": comercio_id} if comercio_id else {}).all()
    if not comercios:
        raise ErrorDeNegocio(409, "No hay comercios abiertos para simular un pedido")
    comercio = rng.choice(comercios)
    productos = db.scalars(
        select(Product).where(Product.merchant_id == comercio.id, Product.is_available.is_(True)).order_by(Product.id)
    ).all()
    if not productos:
        raise ErrorDeNegocio(409, "Ese comercio no tiene productos disponibles")
    elegidos = rng.sample(productos, k=rng.randint(1, min(3, len(productos))))
    barrio, lat, lon = _destino_cerca(rng, comercio.lat, comercio.lon)
    datos = OrderCreateIn(
        merchant_id=comercio.id,
        items=[ItemIn(product_id=p.id, quantity=rng.randint(1, 2)) for p in elegidos],
        delivery_address=f"Casa de prueba en {barrio} (demo)",
        delivery_lat=lat,
        delivery_lon=lon,
        notes=marca,
    )
    _, cuerpo, _ = crear_pedido(db, r, usuario, datos, f"sim-{uuid.uuid4()}")
    return cuerpo
