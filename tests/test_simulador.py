import json
import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.zone import dentro_de_montevideo
from app.models import Courier, DispatchOffer, Merchant, Order, OrderEvent, User
from app.seed import COMERCIOS, SIMULADOS, seed_demo
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
    for nombre in SIMULADOS:
        c = sesion.scalar(select(Courier).join(User).where(User.username == nombre))
        assert c.status == "available" and c.last_location is not None, nombre
    # Rosa es para probar a mano: el simulador no la toca.
    rosa = sesion.scalar(select(Courier).join(User).where(User.username == "rosa"))
    assert rosa.status == "offline" and rosa.last_location is None


def test_los_que_no_son_de_la_demo_no_se_tocan(sesion, redis_test):
    seed_demo(sesion)
    persona = crear_repartidor(sesion)
    tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(1))
    sesion.expire_all()
    assert sesion.get(Courier, persona.id).last_location is None
    assert sesion.get(Courier, persona.id).status == "offline"


def test_los_libres_se_pasean_poco_y_dentro_de_montevideo(sesion, redis_test):
    luis = simulado(sesion, "luis")
    antes = (-34.9120, -56.1520)   # no coincide con ninguna base: siempre tiene hacia dónde ir
    colocar(sesion, luis, *antes)
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
    assert cliente.post("/demo/simulate-order").status_code == 401   # sin sesión no hay botón


def test_el_boton_sin_comercios_explica_que_pasa(cliente, sesion):
    yo = crear_cliente(sesion)
    r = cliente.post("/demo/simulate-order", headers=cabecera(yo.id))
    assert r.status_code == 409 and "comercios" in r.json()["detail"]


def test_los_destinos_de_la_demo_estan_dentro_de_la_zona():
    from app.services.demo import DESTINOS

    assert len(DESTINOS) >= 10
    for barrio, lat, lon in DESTINOS:
        assert dentro_de_montevideo(lat, lon), barrio


def test_el_destino_simulado_es_uno_de_la_lista_y_no_queda_pegado_al_comercio():
    from app.services.demo import DESTINOS, _destino_cerca

    for semilla in range(30):
        barrio, lat, lon = _destino_cerca(random.Random(semilla), -34.9100, -56.1500)
        assert (barrio, lat, lon) in DESTINOS
        assert 400 <= distancia_m(-34.9100, -56.1500, lat, lon) <= 5000


def test_el_repartidor_sigue_la_ruta_por_las_esquinas_hasta_el_comercio(sesion, redis_test):
    """Con calles en cuadrícula (primero al oeste, después al sur), la moto nunca corta camino por los edificios."""
    from tests.helpers import RouterFalso, ruta_en_L
    from app.services.routing import usar_router

    usar_router(RouterFalso(ruta=ruta_en_L))
    luis = simulado(sesion, "luis")
    inicio = (LAT + 0.02, LON + 0.02)
    colocar(sesion, luis, *inicio, estado="busy")
    pedido_id = crear_pedido(sesion, "asignado")
    sesion.get(Order, pedido_id).courier_id = luis.id
    sesion.commit()
    cfg = Config(velocidad_ms=40.0, generar_pedidos=False, demora_oferta_s=(0, 0), demora_comercio_s=(0, 0))
    esquina_vista, estado = False, "asignado"
    for _ in range(40):
        tick(sesion, redis_test, cfg=cfg, rng=random.Random(1))
        lat, lon = ubicacion(sesion, luis.id)
        sobre_la_primera_calle = abs(lat - inicio[0]) < 2e-5 and LON - 1e-4 <= lon <= inicio[1] + 1e-4
        sobre_la_segunda_calle = abs(lon - LON) < 2e-5 and LAT - 1e-4 <= lat <= inicio[0] + 1e-4
        if estado == "asignado":
            assert sobre_la_primera_calle or sobre_la_segunda_calle, (lat, lon)   # jamás en diagonal
            esquina_vista = esquina_vista or sobre_la_segunda_calle
        sesion.expire_all()
        estado = sesion.get(Order, pedido_id).status
        if estado != "asignado":
            break
    assert esquina_vista, "tendría que haber doblado en la esquina"
    assert estado == "en_camino"


def test_al_aparecer_los_repartidores_se_ajustan_a_la_calle(sesion, redis_test):
    from tests.helpers import RouterFalso
    from app.services.routing import usar_router

    ajustados = []

    def ajustar(punto):
        ajustados.append(punto)
        return (punto[0] + 0.0001, punto[1]), 7.0   # «la calle está un poquito al norte»

    usar_router(RouterFalso(ajustar=ajustar))
    seed_demo(sesion)
    tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(1))
    assert len(ajustados) >= 3   # uno por cada repartidor simulado


def test_los_repartidores_libres_van_de_un_punto_en_tierra_a_otro_por_la_ruta(sesion, redis_test):
    """Los destinos de paseo son comercios o barrios de la lista (puntos verificados en tierra), nunca puntos al azar."""
    from tests.helpers import RouterFalso
    from app.services.demo import DESTINOS
    from app.services.routing import usar_router

    router = RouterFalso()
    usar_router(router)
    seed_demo(sesion)
    bases = [(d[1], d[2]) for d in DESTINOS] + [(c["lat"], c["lon"]) for c in COMERCIOS]
    for _ in range(20):
        tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=random.Random(5))
    destinos = [ruta[-1] for ruta in router.pedidos_de_ruta]
    assert destinos and all(min(distancia_m(*d, *b) for b in bases) < 1 for d in destinos)


def test_real_los_repartidores_de_la_demo_siempre_estan_sobre_una_calle(sesion, redis_test):
    """Contra el OSRM real: después de muchas vueltas, nadie está en el agua ni dentro de una manzana."""
    import httpx

    from app.core.config import settings
    from app.services.routing import ConRespaldo, OsrmRouter, RectaRouter, usar_router

    try:
        httpx.get(f"{settings.osrm_url}/nearest/v1/driving/-56.15,-34.91", timeout=1.5).raise_for_status()
    except Exception:
        pytest.skip("OSRM no está corriendo (docker compose up -d osrm)")
    osrm = OsrmRouter(settings.osrm_url)
    usar_router(ConRespaldo(osrm, RectaRouter()))
    seed_demo(sesion)
    rng = random.Random(3)
    for _ in range(40):
        tick(sesion, redis_test, cfg=SIN_PEDIDOS, rng=rng)
        for nombre in SIMULADOS:
            rep = sesion.scalar(select(Courier).join(User).where(User.username == nombre))
            lat, lon = ubicacion(sesion, rep.id)
            assert osrm.ajustar((lat, lon))[1] < 25, (nombre, lat, lon)
