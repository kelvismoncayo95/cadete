import pytest
from sqlalchemy import select

from app.models import Merchant, Order, User
from app.seed import seed_demo
from app.services.couriers import buscar_repartidor_mas_cercano
from app.services.demo import MARCA, MARCA_DEMO
from app.services.routing import usar_router
from tests.helpers import RouterFalso, cabecera, crear_comercio, repartidor_en

LAT, LON = -34.90, -56.15


def usuario(sesion, nombre) -> User:
    return sesion.scalar(select(User).where(User.username == nombre))


def ultimo_pedido(sesion) -> Order:
    sesion.expire_all()
    return sesion.scalars(select(Order).order_by(Order.created_at.desc())).first()


# ---------------------------------------------------------------- el comercio también puede simular un pedido
def test_el_comercio_recibe_un_pedido_de_prueba_que_el_opera_a_mano(cliente, sesion):
    seed_demo(sesion)
    dueno = usuario(sesion, "sushi")
    r = cliente.post("/demo/simulate-order", headers=cabecera(dueno.id))
    assert r.status_code == 201 and r.json()["status"] == "recibido"
    pedido = ultimo_pedido(sesion)
    assert sesion.get(Merchant, pedido.merchant_id).user_id == dueno.id        # es de SU comercio
    assert sesion.get(User, pedido.customer_user_id).username in ("ana", "pedro")
    # No lleva la marca de «simulado»: el simulador NO lo toca, lo atiende la persona desde el tablero.
    assert pedido.notes == MARCA_DEMO and pedido.notes != MARCA


# ---------------------------------------------------------------- el repartidor recibe un pedido cerca de donde está
def test_el_repartidor_sin_posicion_recibe_una_explicacion(cliente, sesion):
    seed_demo(sesion)
    r = cliente.post("/demo/simulate-order", headers=cabecera(usuario(sesion, "rosa").id))
    assert r.status_code == 409 and "mapa" in r.json()["detail"]


def test_el_repartidor_recibe_un_pedido_del_comercio_mas_cercano_a_su_posicion(cliente, sesion):
    from app.models import Courier

    seed_demo(sesion)
    rosa = sesion.scalar(select(Courier).where(Courier.user_id == usuario(sesion, "rosa").id))
    rosa.last_location = "SRID=4326;POINT(-56.2005 -34.9062)"   # al lado del Café del Puerto (Ciudad Vieja)
    sesion.commit()
    r = cliente.post("/demo/simulate-order", headers=cabecera(rosa.user_id))
    assert r.status_code == 201
    pedido = ultimo_pedido(sesion)
    assert sesion.get(Merchant, pedido.merchant_id).name.startswith("Café del Puerto")
    assert pedido.notes == MARCA   # este SÍ lo atiende el simulador (hace de comercio); ella hace de repartidora


def test_el_administrador_tambien_puede_generar_un_pedido(cliente, sesion):
    seed_demo(sesion)
    r = cliente.post("/demo/simulate-order", headers=cabecera(usuario(sesion, "admin").id))
    assert r.status_code == 201 and ultimo_pedido(sesion).notes == MARCA


# ---------------------------------------------------------------- los repartidores «humanos» tienen prioridad
def tabla_por_latitud(tiempos):
    return lambda origenes, destino: [tiempos.get(round(lat, 4)) for lat, lon in origenes]


def test_el_repartidor_prioritario_recibe_la_oferta_aunque_otro_llegue_mas_rapido(sesion, monkeypatch):
    from app.core.config import settings

    comercio, _ = crear_comercio(sesion)
    humano = repartidor_en(sesion, LAT + 0.0135, LON)    # lento por calle
    simulado = repartidor_en(sesion, LAT + 0.0045, LON)  # rápido
    usar_router(RouterFalso(tabla=tabla_por_latitud({round(LAT + 0.0135, 4): (900.0, 2600.0), round(LAT + 0.0045, 4): (100.0, 700.0)})))
    assert buscar_repartidor_mas_cercano(sesion, comercio.id).courier.id == simulado.id     # sin prioridad gana el rápido
    sesion.rollback()
    nombre = sesion.scalar(select(User.username).where(User.id == humano.user_id))
    monkeypatch.setattr(settings, "repartidores_prioritarios", nombre)
    assert buscar_repartidor_mas_cercano(sesion, comercio.id).courier.id == humano.id        # con prioridad gana el humano


def test_si_el_prioritario_no_esta_disponible_se_ofrece_a_los_demas(sesion, monkeypatch):
    from app.core.config import settings

    comercio, _ = crear_comercio(sesion)
    ocupado = repartidor_en(sesion, LAT + 0.0045, LON, estado="busy")
    otro = repartidor_en(sesion, LAT + 0.0135, LON)
    monkeypatch.setattr(settings, "repartidores_prioritarios", sesion.scalar(select(User.username).where(User.id == ocupado.user_id)))
    assert buscar_repartidor_mas_cercano(sesion, comercio.id).courier.id == otro.id


def test_la_lista_de_prioritarios_acepta_varios_nombres(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "repartidores_prioritarios", " rosa , nico ")
    assert settings.prioritarios == {"rosa", "nico"}
