"""Datos de demo: usuarios (los comercios se agregan en el paso 7, con sus coordenadas).

Uso:  python -m app.seed
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hashear
from app.models import Courier, User

# Contraseña PÚBLICA de la demo (la misma que minipay). Solo protege datos inventados.
# NO reutilizar contraseñas personales.
DEMO_PASSWORD = "demo1234"

CLIENTES = [("ana", "Ana"), ("pedro", "Pedro")]
REPARTIDORES = [("luis", "Luis", "moto"), ("marta", "Marta", "bici"), ("diego", "Diego", "moto")]
ADMINS = [("admin", "Administrador")]


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


if __name__ == "__main__":
    from app.core.database import SessionLocal

    with SessionLocal() as s:
        seed_usuarios(s)
    print("Usuarios de demo listos.")
