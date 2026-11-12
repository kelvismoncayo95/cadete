"""Datos de demo: usuarios, comercios y productos de Montevideo. Todo inventado.

Uso:  python -m app.seed
"""
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hashear
from app.models import Courier, Merchant, Product, User

# Contraseña PÚBLICA de la demo (la misma que minipay). Solo protege datos inventados.
# NO reutilizar contraseñas personales.
DEMO_PASSWORD = "demo1234"

CLIENTES = [("ana", "Ana"), ("pedro", "Pedro")]
REPARTIDORES = [("luis", "Luis", "moto"), ("marta", "Marta", "bici"), ("diego", "Diego", "moto"),
                ("rosa", "Rosa", "bici")]
# Los maneja el simulador. Rosa NO: es para que quien visita la demo pruebe el rol de repartidor a mano.
SIMULADOS = ("luis", "marta", "diego")
ADMINS = [("admin", "Administrador")]


# Comercios inventados, repartidos por barrios de Montevideo. Precios en centavos ($150 = 15000).
# Las coordenadas son aproximadas; se afinan en el paso 11, mirando el mapa.
COMERCIOS = [
    {"username": "pizzeria", "name": "Pizzería La Rambla (demo)", "category": "pizzería",
     "address": "Barrio Pocitos", "lat": -34.9100, "lon": -56.1500,
     "productos": [("Pizza muzzarella", 35000), ("Pizza napolitana", 42000), ("Fainá", 8000),
                   ("Gaseosa 500 ml", 9000)]},
    {"username": "cafe", "name": "Café del Puerto (demo)", "category": "café",
     "address": "Ciudad Vieja", "lat": -34.9060, "lon": -56.2010,
     "productos": [("Café con leche", 12000), ("Medialuna", 6000), ("Tostado mixto", 22000),
                   ("Jugo de naranja", 14000)]},
    {"username": "almacen", "name": "Almacén Cordón (demo)", "category": "almacén",
     "address": "Barrio Cordón", "lat": -34.9040, "lon": -56.1790,
     "productos": [("Pan del día", 7000), ("Leche 1 L", 5500), ("Queso en fetas", 18000),
                   ("Yerba 1 kg", 21000)]},
    {"username": "sushi", "name": "Sushi Punta (demo)", "category": "sushi",
     "address": "Punta Carretas", "lat": -34.9230, "lon": -56.1580,
     "productos": [("Combo 10 piezas", 56000), ("Combo 20 piezas", 98000), ("Gyozas", 24000),
                   ("Té frío", 10000)]},
    {"username": "panaderia", "name": "Panadería del Parque (demo)", "category": "panadería",
     "address": "Parque Rodó", "lat": -34.9150, "lon": -56.1650,
     "productos": [("Pan francés", 6500), ("Bizcochos surtidos", 15000), ("Torta frita", 4000),
                   ("Chivito al pan", 30000)]},
]


def _asegurar_usuario(session: Session, username: str, nombre: str, rol: str, hash_demo: str) -> User:
    usuario = session.scalar(select(User).where(User.username == username))
    if usuario is None:
        usuario = User(username=username, display_name=nombre, role=rol, password_hash=hash_demo)
        session.add(usuario)
        session.flush()
    return usuario


def seed_usuarios(session: Session) -> None:
    """Crea los usuarios de demo si no existen (se puede correr muchas veces)."""
    hash_demo = hashear(DEMO_PASSWORD)
    for username, nombre in CLIENTES:
        _asegurar_usuario(session, username, nombre, "customer", hash_demo)
    for username, nombre in ADMINS:
        _asegurar_usuario(session, username, nombre, "admin", hash_demo)
    for username, nombre, vehiculo in REPARTIDORES:
        usuario = _asegurar_usuario(session, username, nombre, "courier", hash_demo)
        if session.scalar(select(Courier).where(Courier.user_id == usuario.id)) is None:
            session.add(Courier(user_id=usuario.id, vehicle=vehiculo))
    session.commit()


def usuarios_de_demo() -> list[dict]:
    """La lista pública de usuarios de demo (para la pantalla de entrada)."""
    lista = [{"username": u, "display_name": n, "role": "customer", "simulated": False} for u, n in CLIENTES]
    lista += [{"username": c["username"], "display_name": c["name"], "role": "merchant", "simulated": False}
              for c in COMERCIOS]
    lista += [{"username": u, "display_name": n, "role": "courier", "simulated": u in SIMULADOS}
              for u, n, _ in REPARTIDORES]
    lista += [{"username": u, "display_name": n, "role": "admin", "simulated": False} for u, n in ADMINS]
    return lista


def seed_comercios(session: Session) -> None:
    """Crea los comercios de demo con sus productos, si no existen."""
    hash_demo = hashear(DEMO_PASSWORD)
    for datos in COMERCIOS:
        dueno = _asegurar_usuario(session, datos["username"], datos["name"], "merchant", hash_demo)
        comercio = session.scalar(select(Merchant).where(Merchant.user_id == dueno.id))
        if comercio is None:
            comercio = Merchant(
                user_id=dueno.id, name=datos["name"], category=datos["category"], address=datos["address"],
                location=WKTElement(f"POINT({datos['lon']} {datos['lat']})", srid=4326),
            )
            session.add(comercio)
            session.flush()
        existentes = set(session.scalars(select(Product.name).where(Product.merchant_id == comercio.id)))
        for nombre, precio in datos["productos"]:
            if nombre not in existentes:
                session.add(Product(merchant_id=comercio.id, name=nombre, price_cents=precio))
    session.commit()


def seed_demo(session: Session) -> None:
    seed_usuarios(session)
    seed_comercios(session)


if __name__ == "__main__":
    from app.core.database import SessionLocal

    with SessionLocal() as s:
        seed_demo(s)
    print("Datos de demo listos.")
