import json
import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.zone import dentro_de_montevideo
from app.models import Courier, DispatchOffer, Merchant, Order, OrderEvent, User
from app.seed import seed_demo
from app.services.demo import MARCA
from app.services.dispatch import despachar_pedido
from app.services.events import CANAL_TODO
from app.services.geo import distancia_m
from app.simulator.engine import Config, tick
from tests.helpers import cabecera, crear_cliente, crear_pedido, crear_repartidor, punto

LAT, LON = -34.90, -56.15  # el comercio de crear_pedido
SIN_PEDIDOS = Config(generar_pedidos=False, demora_oferta_s=(0, 0), demora_comercio_s=(0, 0))


def simulado(sesion, nombre) -> Courier:
    seed_demo(sesion)
    usuario = sesion.scalar(select(User).where(User.username == nombre))
    return sesion.scalar(select(Courier).where(Courier.user_id == usuario.id))


def colocar(sesion, repartidor: Courier, lat, lon, estado="available"):
    repartidor.last_location = punto(lon, lat)
    repartidor.status = estado
    sesion.commit()


def ubicacion(sesion, repartidor_id):
    from geoalchemy2 import Geometry
    from sqlalchemy import cast

    sesion.expire_all()
    g = cast(Courier.last_location, Geometry)
    return sesion.execute(select(func.ST_Y(g), func.ST_X(g)).where(Courier.id == repartidor_id)).one()


def alejar_a_los_demas(sesion, quien: str):
    for otro in sesion.scalars(select(Courier).join(User).where(User.username != quien)):
        if otro.last_location is None:
            colocar(sesion, otro, LAT + 0.3, LON)
    return


def test_los_repartidores_de_la_demo_aparecen_disponibles_y_con_posicion(sesion, redis_test):
    seed_demo(sesion)
    tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(1))
    sesion.expire_all()
    for c in sesion.scalars(select(Courier)):
        assert c.status == "available" and c.last_location is not None


def test_los_que_no_son_de_la_demo_no_se_tocan(sesion, redis_test):
    seed_demo(sesion)
    persona = crear_repartidor(sesion)
    tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(1))
    sesion.expire_all()
    assert sesion.get(Courier, persona.id).last_location is None
    assert sesion.get(Courier, persona.id).status == "offline"


def test_los_libres_se_pasean_poco_y_dentro_de_montevideo(sesion, redis_test):
    luis = simulado(sesion, "luis")
    colocar(sesion, luis, -34.91, -56.15)
    antes = (-34.91, -56.15)
    tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(7))
    despues = ubicacion(sesion, luis.id)
    assert 0 < distancia_m(*antes, *despues) <= 25.0 * 5  # a lo sumo lo que avanza en una vuelta
    assert dentro_de_montevideo(*despues)


def test_acepta_la_oferta_que_le_llega(sesion, redis_test):
    luis = simulado(sesion, "luis")
    colocar(sesion, luis, LAT + 0.001, LON)
    alejar_a_los_demas(sesion, "luis")
    pedido_id = crear_pedido(sesion, "listo")
    despachar_pedido(sesion, pedido_id)
    sesion.commit()
    cfg = Config(prob_aceptar=1.0, prob_rechazar=0.0, generar_pedidos=False, demora_oferta_s=(0, 0), demora_comercio_s=(0, 0))
    tick(sesion, redis_test, cfg=cfg, rng=random.Random(1))
    sesion.expire_all()
    pedido = sesion.get(Order, pedido_id)
    assert (pedido.status, pedido.courier_id) == ("asignado", luis.id)


def test_puede_rechazar_y_entonces_pasa_al_siguiente(sesion, redis_test):
    luis, marta = simulado(sesion, "luis"), simulado(sesion, "marta")
    colocar(sesion, luis, LAT + 0.001, LON)
    colocar(sesion, marta, LAT + 0.01, LON)
    alejar_a_los_demas(sesion, "luis")  # diego, lejos: así el siguiente de la fila es marta
    pedido_id = crear_pedido(sesion, "listo")
    despachar_pedido(sesion, pedido_id)
    sesion.commit()
    cfg = Config(prob_aceptar=0.0, prob_rechazar=1.0, generar_pedidos=False, demora_oferta_s=(0, 0), demora_comercio_s=(0, 0))
    tick(sesion, redis_test, cfg=cfg, rng=random.Random(1))
    sesion.expire_all()
    estados = {o.courier_id: o.status for o in sesion.scalars(select(DispatchOffer).where(DispatchOffer.order_id == pedido_id))}
    assert estados[luis.id] == "rechazada" and estados[marta.id] in ("pendiente", "rechazada")


def test_a_veces_ignora_la_oferta_y_se_deja_vencer(sesion, redis_test):
    luis = simulado(sesion, "luis")
    colocar(sesion, luis, LAT + 0.001, LON)
    alejar_a_los_demas(sesion, "luis")
    pedido_id = crear_pedido(sesion, "listo")
    despachar_pedido(sesion, pedido_id)
    sesion.commit()
    cfg = Config(prob_aceptar=0.0, prob_rechazar=0.0, generar_pedidos=False, demora_oferta_s=(0, 0), demora_comercio_s=(0, 0))
    tick(sesion, redis_test, cfg=cfg, rng=random.Random(1))
    sesion.expire_all()
    assert sesion.scalars(select(DispatchOffer).where(DispatchOffer.order_id == pedido_id)).one().status == "pendiente"


def test_lleva_el_pedido_al_comercio_y_despues_al_cliente(sesion, redis_test):
    luis = simulado(sesion, "luis")
    colocar(sesion, luis, LAT + 0.02, LON, estado="busy")  # a ~2 km del comercio
    pedido_id = crear_pedido(sesion, "asignado")
    sesion.get(Order, pedido_id).courier_id = luis.id
    sesion.commit()
    cfg = Config(velocidad_ms=1000.0, generar_pedidos=False, demora_oferta_s=(0, 0), demora_comercio_s=(0, 0))
    vistos = []
    for _ in range(10):
        tick(sesion, redis_test, cfg=cfg, rng=random.Random(1))
        sesion.expire_all()
        vistos.append(sesion.get(Order, pedido_id).status)
        if vistos[-1] == "entregado":
            break
    assert "en_camino" in vistos and vistos[-1] == "entregado"
    assert sesion.get(Courier, luis.id).status == "available"
    actores = set(sesion.scalars(select(OrderEvent.actor_user_id).where(OrderEvent.order_id == pedido_id)))
    assert luis.user_id in actores


def test_el_comercio_simulado_prepara_solo_los_pedidos_marcados(sesion, redis_test):
    simulado(sesion, "luis")
    marcado, ajeno = crear_pedido(sesion), crear_pedido(sesion)
    sesion.get(Order, marcado).notes = MARCA
    sesion.commit()
    for _ in range(4):
        tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(1))
    sesion.expire_all()
    assert sesion.get(Order, marcado).status in ("listo", "asignado", "en_camino", "entregado")
    assert sesion.get(Order, ajeno).status == "recibido"


def test_genera_un_pedido_de_juguete_si_no_hay_ninguno_activo(sesion, redis_test):
    seed_demo(sesion)
    cfg = Config(generar_pedidos=True, demora_oferta_s=(0, 0), demora_comercio_s=(100, 100))
    tick(sesion, redis_test, cfg=cfg, rng=random.Random(3))
    tick(sesion, redis_test, cfg=cfg, rng=random.Random(4))  # ya hay uno activo: no crea otro
    pedidos = sesion.scalars(select(Order)).all()
    assert len(pedidos) == 1
    assert pedidos[0].notes == MARCA and pedidos[0].status == "recibido"
    assert sesion.get(User, pedidos[0].customer_user_id).username in ("ana", "pedro")


def test_sin_generar_pedidos_no_crea_ninguno(sesion, redis_test):
    seed_demo(sesion)
    tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(3))
    assert sesion.scalar(select(func.count()).select_from(Order)) == 0


def test_cada_vuelta_publica_las_posiciones_para_el_mapa(sesion, redis_test):
    seed_demo(sesion)
    ps = redis_test.pubsub(ignore_subscribe_messages=True)
    ps.subscribe(CANAL_TODO)
    ps.get_message(timeout=1)
    tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(1))
    tipos = []
    for _ in range(20):
        m = ps.get_message(timeout=0.2)
        if m:
            tipos.append(json.loads(m["data"])["tipo"])
        if tipos.count("repartidor") >= 3:
            break
    ps.close()
    assert tipos.count("repartidor") >= 3


def test_el_boton_simular_un_pedido(cliente, sesion):
    from app.seed import seed_comercios

    seed_comercios(sesion)
    yo = crear_cliente(sesion)
    r = cliente.post("/demo/simulate-order", headers=cabecera(yo.id))
    assert r.status_code == 201 and r.json()["status"] == "recibido"
    assert sesion.get(Order, r.json()["id"]).notes == MARCA
    assert cliente.post("/demo/simulate-order", headers=cabecera(sesion.scalar(select(User.id).where(User.role == "merchant")))).status_code == 403


def test_el_boton_sin_comercios_explica_que_pasa(cliente, sesion):
    yo = crear_cliente(sesion)
    r = cliente.post("/demo/simulate-order", headers=cabecera(yo.id))
    assert r.status_code == 409 and "comercios" in r.json()["detail"]
