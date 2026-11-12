from sqlalchemy import func, select

from app.core.zone import dentro_de_montevideo
from app.models import Merchant, Product
from app.seed import COMERCIOS, DEMO_PASSWORD, seed_comercios


def test_los_comercios_de_demo_estan_en_montevideo_y_son_inventados():
    assert len(COMERCIOS) == 5
    for c in COMERCIOS:
        assert dentro_de_montevideo(c["lat"], c["lon"]), c["name"]
        assert "(demo)" in c["name"]
        assert len(c["productos"]) >= 4


def test_seed_crea_comercios_con_productos(sesion):
    seed_comercios(sesion)
    assert sesion.scalar(select(func.count()).select_from(Merchant)) == 5
    assert sesion.scalar(select(func.count()).select_from(Product)) == sum(len(c["productos"]) for c in COMERCIOS)


def test_seed_de_comercios_es_repetible(sesion):
    seed_comercios(sesion)
    seed_comercios(sesion)
    assert sesion.scalar(select(func.count()).select_from(Merchant)) == 5


def test_el_dueno_de_un_comercio_puede_entrar(cliente, sesion):
    seed_comercios(sesion)
    r = cliente.post("/auth/login", json={"username": COMERCIOS[0]["username"], "password": DEMO_PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "merchant"


def test_el_catalogo_muestra_los_comercios_sembrados(cliente, sesion):
    from app.seed import seed_usuarios

    seed_usuarios(sesion)
    seed_comercios(sesion)
    token = cliente.post("/auth/login", json={"username": "ana", "password": DEMO_PASSWORD}).json()["access_token"]
    r = cliente.get("/merchants", headers={"Authorization": f"Bearer {token}"})
    assert len(r.json()) == 5
