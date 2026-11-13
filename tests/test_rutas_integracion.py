import json
import math

import pytest

from app.models import Courier, Merchant, Order, User
from app.services.couriers import buscar_repartidor_mas_cercano
from app.services.dispatch import despachar_pedido
from app.services.events import canal_pedido, datos_de_pedido
from app.services.geo import distancia_m
from app.services.routing import Ruta, usar_router
from tests.helpers import (
    RouterFalso, cabecera, crear_cliente, crear_comercio, crear_pedido, crear_repartidor, cuerpo_pedido,
    repartidor_en, ruta_en_L,
)

LAT, LON = -34.90, -56.15   # el comercio de crear_pedido / crear_comercio


def tabla_por_latitud(tiempos: dict):
    """Tiempos por calle según la latitud del repartidor: {(lat redondeada): (segundos, metros) o None}."""
    def tabla(origenes, destino):
        return [tiempos.get(round(lat, 4)) for lat, lon in origenes]
    return tabla


# ---------------------------------------------------------------- el «más cercano» es por tiempo por calle
def test_el_mas_cercano_es_el_de_menor_tiempo_por_calle_no_el_de_menor_distancia_en_recta(sesion):
    comercio, _ = crear_comercio(sesion)
    cerca_en_recta = repartidor_en(sesion, LAT + 0.0045, LON)     # a 500 m en recta...
    lejos_en_recta = repartidor_en(sesion, LAT + 0.0135, LON)     # a 1,5 km en recta
    usar_router(RouterFalso(tabla=tabla_por_latitud({
        round(LAT + 0.0045, 4): (900.0, 2600.0),    # ...pero tiene que dar una vuelta enorme (río, sentido único)
        round(LAT + 0.0135, 4): (200.0, 1700.0),
    })))
    elegido = buscar_repartidor_mas_cercano(sesion, comercio.id)
    assert elegido.courier.id == lejos_en_recta.id
    assert elegido.distancia_m == 1700.0   # la distancia que se informa es por calle
    assert elegido.courier.id != cerca_en_recta.id


def test_se_saltea_a_los_que_no_tienen_camino(sesion):
    comercio, _ = crear_comercio(sesion)
    isla = repartidor_en(sesion, LAT + 0.0045, LON)
    repartidor_en(sesion, LAT + 0.0135, LON)
    usar_router(RouterFalso(tabla=tabla_por_latitud({round(LAT + 0.0045, 4): None, round(LAT + 0.0135, 4): (300.0, 1700.0)})))
    assert buscar_repartidor_mas_cercano(sesion, comercio.id).courier.id != isla.id


def test_si_nadie_tiene_camino_no_hay_candidato(sesion):
    comercio, _ = crear_comercio(sesion)
    repartidor_en(sesion, LAT + 0.0045, LON)
    usar_router(RouterFalso(tabla=lambda o, d: [None] * len(o)))
    assert buscar_repartidor_mas_cercano(sesion, comercio.id) is None


def test_dos_pedidos_simultaneos_siguen_sin_recibir_al_mismo_repartidor(migrada, sesion):
    from sqlalchemy.orm import Session

    comercio, _ = crear_comercio(sesion)
    mejor = repartidor_en(sesion, LAT + 0.0135, LON)
    otro = repartidor_en(sesion, LAT + 0.0045, LON)
    usar_router(RouterFalso(tabla=tabla_por_latitud({round(LAT + 0.0135, 4): (200.0, 1700.0), round(LAT + 0.0045, 4): (900.0, 2600.0)})))
    with Session(migrada) as a, Session(migrada) as b:
        primero = buscar_repartidor_mas_cercano(a, comercio.id).courier.id    # a bloquea al mejor por calle
        segundo = buscar_repartidor_mas_cercano(b, comercio.id).courier.id    # b toma al siguiente
        a.rollback(); b.rollback()
    assert (primero, segundo) == (mejor.id, otro.id)


def test_la_oferta_guarda_la_distancia_por_calle(sesion):
    pedido_id = crear_pedido(sesion, "listo")
    repartidor_en(sesion, LAT + 0.0045, LON)
    usar_router(RouterFalso(tabla=lambda o, d: [(240.0, 1234.0)] * len(o)))
    oferta = despachar_pedido(sesion, pedido_id)
    assert oferta.distance_m == 1234


# ---------------------------------------------------------------- ruta y tiempo estimado en los eventos
def pedido_asignado(sesion, estado="asignado"):
    pedido_id = crear_pedido(sesion, estado)
    rep = repartidor_en(sesion, LAT + 0.0045, LON, estado="busy")
    sesion.get(Order, pedido_id).courier_id = rep.id
    sesion.commit()
    return pedido_id, rep


def test_el_evento_trae_la_ruta_por_calles_como_lon_lat(sesion):
    pedido_id, rep = pedido_asignado(sesion, "en_camino")
    esquina = (LAT + 0.0045, -56.16)
    usar_router(RouterFalso(ruta=lambda puntos: Ruta(1500.0, 600.0, [puntos[0], esquina, puntos[-1]])))
    datos = datos_de_pedido(sesion, sesion.get(Order, pedido_id))
    assert datos["route"][1] == [esquina[1], esquina[0]]   # GeoJSON: [lon, lat]
    assert len(datos["route"]) == 3


def test_el_tiempo_estimado_sale_de_la_duracion_de_la_ruta(sesion):
    pedido_id, rep = pedido_asignado(sesion, "en_camino")
    usar_router(RouterFalso(ruta=lambda puntos: Ruta(1500.0, 600.0, list(puntos))))
    assert datos_de_pedido(sesion, sesion.get(Order, pedido_id))["eta_min"] == 10


def test_con_demo_acelerada_el_tiempo_estimado_se_reduce(sesion, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "aceleracion_demo", 3.0)
    pedido_id, rep = pedido_asignado(sesion, "en_camino")
    usar_router(RouterFalso(ruta=lambda puntos: Ruta(1500.0, 600.0, list(puntos))))
    assert datos_de_pedido(sesion, sesion.get(Order, pedido_id))["eta_min"] == 4   # 600 s / 3 = 200 s → 4 min


def test_asignado_la_ruta_pasa_primero_por_el_comercio(sesion):
    pedido_id, rep = pedido_asignado(sesion, "asignado")
    router = RouterFalso()
    usar_router(router)
    datos_de_pedido(sesion, sesion.get(Order, pedido_id))
    puntos = router.pedidos_de_ruta[-1]
    assert len(puntos) == 3 and puntos[1] == pytest.approx((LAT, LON))   # repartidor → comercio → cliente


def test_sin_repartidor_la_ruta_va_del_comercio_al_cliente_y_no_hay_tiempo_estimado(sesion):
    pedido_id = crear_pedido(sesion, "preparando")
    datos = datos_de_pedido(sesion, sesion.get(Order, pedido_id))
    assert len(datos["route"]) >= 2 and datos["eta_min"] is None


def test_cada_posicion_nueva_publica_la_ruta_desde_ahi(cliente, sesion, redis_test):
    pedido_id, rep = pedido_asignado(sesion, "en_camino")
    ps = redis_test.pubsub(ignore_subscribe_messages=True)
    ps.subscribe(canal_pedido(pedido_id))
    ps.get_message(timeout=1)
    router = RouterFalso(ruta=lambda puntos: Ruta(900.0, 300.0, list(puntos)))
    usar_router(router)
    cliente.post("/courier/location", json={"lat": LAT + 0.004, "lon": LON}, headers=cabecera(rep.user_id))
    mensaje = None
    for _ in range(20):
        m = ps.get_message(timeout=0.2)
        if m:
            mensaje = json.loads(m["data"])
            break
    ps.close()
    assert mensaje["tipo"] == "posicion" and mensaje["eta_min"] == 5
    assert mensaje["route"][0] == [LON, LAT + 0.004]   # la ruta nace en la posición nueva


# ---------------------------------------------------------------- destinos y posiciones sobre una calle
def test_un_destino_lejos_de_toda_calle_se_rechaza(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    usar_router(RouterFalso(ajustar=lambda p: (p, 800.0)))   # a 800 m de la calle más cercana: el agua
    r = cliente.post("/orders", json=cuerpo_pedido(comercio, [(pizza, 1)]), headers={**cabecera(yo.id), "Idempotency-Key": "k1"})
    assert r.status_code == 422
    assert r.json()["detail"] == "Ese punto no está sobre una calle. Marcá un punto más cerca de una calle."


def test_un_destino_junto_a_una_calle_se_acepta(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    usar_router(RouterFalso(ajustar=lambda p: (p, 20.0)))
    r = cliente.post("/orders", json=cuerpo_pedido(comercio, [(pizza, 1)]), headers={**cabecera(yo.id), "Idempotency-Key": "k2"})
    assert r.status_code == 201


def test_la_posicion_del_repartidor_se_ajusta_a_la_calle(cliente, sesion):
    from geoalchemy2 import Geometry
    from sqlalchemy import cast, func, select

    rep = crear_repartidor(sesion)
    en_la_calle = (LAT + 0.0001, LON + 0.0001)
    usar_router(RouterFalso(ajustar=lambda p: (en_la_calle, 12.0)))
    assert cliente.post("/courier/location", json={"lat": LAT, "lon": LON}, headers=cabecera(rep.user_id)).status_code == 204
    sesion.expire_all()
    g = cast(Courier.last_location, Geometry)
    assert sesion.execute(select(func.ST_Y(g), func.ST_X(g)).where(Courier.id == rep.id)).one() == pytest.approx(en_la_calle)


def test_una_posicion_en_el_agua_se_rechaza(cliente, sesion):
    rep = crear_repartidor(sesion)
    usar_router(RouterFalso(ajustar=lambda p: (p, 900.0)))
    r = cliente.post("/courier/location", json={"lat": LAT, "lon": LON}, headers=cabecera(rep.user_id))
    assert r.status_code == 422 and "calle" in r.json()["detail"]


# ---------------------------------------------------------------- estado del sistema
def sistema(cliente, sesion):
    admin = sesion.query(User).filter_by(username="adm").first()
    if admin is None:
        admin = User(username="adm", password_hash="h", display_name="Admin", role="admin")
        sesion.add(admin)
        sesion.commit()
    return cliente.get("/admin/system", headers=cabecera(admin.id)).json()


def test_el_estado_del_sistema_informa_si_las_rutas_usan_el_respaldo(cliente, sesion, redis_test):
    from app.services.heartbeat import latir

    latir(redis_test, "worker")
    router = RouterFalso()
    usar_router(router)
    d = sistema(cliente, sesion)
    assert d["checks"]["rutas"] == {"ok": True, "motor": "osrm"} and d["status"] == "ok"
    router.usando_respaldo = True
    d = sistema(cliente, sesion)
    assert d["checks"]["rutas"] == {"ok": False, "motor": "recta"} and d["status"] == "degradado"
