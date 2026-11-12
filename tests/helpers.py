import uuid

from alembic.config import Config
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Merchant, Order, User


def alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.test_db_url.replace("%", "%%"))
    return cfg


def punto(lon: float = -56.16, lat: float = -34.90) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def crear_pedido(session: Session, estado: str = "recibido") -> uuid.UUID:
    """Crea un cliente, un comercio y un pedido de juguete en el estado pedido."""
    sufijo = uuid.uuid4().hex[:8]
    cliente = User(username=f"cli_{sufijo}", password_hash="h", display_name="Cliente", role="customer")
    dueno = User(username=f"com_{sufijo}", password_hash="h", display_name="Comercio", role="merchant")
    session.add_all([cliente, dueno])
    session.flush()
    comercio = Merchant(
        user_id=dueno.id, name="Comercio (demo)", category="comida",
        address="Calle 1", location=punto(-56.15, -34.90),
    )
    session.add(comercio)
    session.flush()
    pedido = Order(
        customer_user_id=cliente.id, merchant_id=comercio.id, status=estado,
        delivery_address="Calle 2", delivery_location=punto(),
        subtotal_cents=10000, delivery_fee_cents=6000, total_cents=16000,
    )
    session.add(pedido)
    session.commit()
    return pedido.id


def crear_repartidor(session: Session):
    from app.models import Courier

    sufijo = uuid.uuid4().hex[:8]
    usuario = User(username=f"rep_{sufijo}", password_hash="h", display_name="Repartidor", role="courier")
    session.add(usuario)
    session.flush()
    repartidor = Courier(user_id=usuario.id, vehicle="moto")
    session.add(repartidor)
    session.commit()
    return repartidor


def cabecera(usuario_id) -> dict[str, str]:
    """Cabecera Authorization con un token válido para ese usuario."""
    from app.core.security import crear_token

    return {"Authorization": f"Bearer {crear_token(usuario_id)}"}


def crear_cliente(session: Session) -> User:
    usuario = User(
        username=f"cli_{uuid.uuid4().hex[:8]}", password_hash="h", display_name="Cliente", role="customer"
    )
    session.add(usuario)
    session.commit()
    return usuario


def crear_comercio(session: Session, abierto: bool = True, productos=(("Pizza", 15000), ("Bebida", 5000))):
    """Comercio de juguete con productos. Devuelve (comercio, [productos])."""
    from app.models import Product

    sufijo = uuid.uuid4().hex[:8]
    dueno = User(username=f"com_{sufijo}", password_hash="h", display_name="Dueño", role="merchant")
    session.add(dueno)
    session.flush()
    comercio = Merchant(
        user_id=dueno.id, name=f"Comercio {sufijo} (demo)", category="comida",
        address="Calle 1", location=punto(-56.15, -34.90), is_open=abierto,
    )
    session.add(comercio)
    session.flush()
    lista = [Product(merchant_id=comercio.id, name=n, price_cents=p) for n, p in productos]
    session.add_all(lista)
    session.commit()
    return comercio, lista


def cuerpo_pedido(comercio, items, lat=-34.90, lon=-56.16) -> dict:
    return {
        "merchant_id": str(comercio.id),
        "items": [{"product_id": str(p.id), "quantity": q} for p, q in items],
        "delivery_address": "Calle 2 123",
        "delivery_lat": lat,
        "delivery_lon": lon,
    }
