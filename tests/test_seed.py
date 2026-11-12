from sqlalchemy import func, select

from app.models import Courier, User
from app.seed import DEMO_PASSWORD, seed_usuarios

NOMBRES = {"ana", "pedro", "luis", "marta", "diego", "admin"}


def test_la_contrasena_de_demo_es_la_de_minipay():
    assert DEMO_PASSWORD == "demo1234"


def test_seed_crea_los_usuarios_de_demo(sesion):
    seed_usuarios(sesion)
    assert set(sesion.scalars(select(User.username))) == NOMBRES
    assert sesion.scalar(select(func.count()).select_from(Courier)) == 3


def test_seed_es_repetible(sesion):
    seed_usuarios(sesion)
    seed_usuarios(sesion)
    assert sesion.scalar(select(func.count()).select_from(User)) == len(NOMBRES)
    assert sesion.scalar(select(func.count()).select_from(Courier)) == 3


def test_todos_pueden_entrar_con_la_contrasena_de_demo(cliente, sesion):
    seed_usuarios(sesion)
    for nombre in NOMBRES:
        r = cliente.post("/auth/login", json={"username": nombre, "password": DEMO_PASSWORD})
        assert r.status_code == 200, nombre
