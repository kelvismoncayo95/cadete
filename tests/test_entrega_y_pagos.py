import json

import pytest
from sqlalchemy import func, select

from app.models import Courier, LedgerEntry, Merchant, Order, User
from app.services.dispatch import despachar_pedido
from app.services.pagos import calcular_pago_repartidor
from app.services.routing import Ruta, usar_router
from tests.helpers import RouterFalso, cabecera, crear_pedido, repartidor_en

LAT, LON = -34.90, -56.15            # el comercio de crear_pedido
DEST_LAT, DEST_LON = -34.90, -56.16  # el destino de crear_pedido (≈ 920 m al oeste)


def pedido_con_repartidor(sesion, estado, lat, lon, pago=11500):
    """Un pedido en ese estado y su repartidor (busy) parado en (lat, lon)."""
    pedido_id = crear_pedido(sesion, estado)
    rep = repartidor_en(sesion, lat, lon, estado="busy")
    pedido = sesion.get(Order, pedido_id)
    pedido.courier_id, pedido.courier_pay_cents = rep.id, pago
    sesion.commit()
    return pedido_id, rep


def accion(cliente, rep, pedido_id, nombre):
    return cliente.post(f"/courier/orders/{pedido_id}/{nombre}", headers=cabecera(rep.user_id))


# ---------------------------------------------------------------- llegar al comercio
def test_no_se_puede_marcar_llegada_lejos_del_comercio(cliente, sesion):
    pedido_id, rep = pedido_con_repartidor(sesion, "asignado", LAT + 0.0045, LON)   # a ≈ 500 m
    r = accion(cliente, rep, pedido_id, "arrived")
    assert r.status_code == 409
    assert "a 500 m del comercio" in r.json()["detail"] and "150 m" in r.json()["detail"]
    assert sesion.get(Order, pedido_id).status == "asignado"


def test_cerca_del_comercio_se_marca_la_llegada(cliente, sesion):
    pedido_id, rep = pedido_con_repartidor(sesion, "asignado", LAT + 0.0001, LON)   # a ≈ 11 m
    r = accion(cliente, rep, pedido_id, "arrived")
    assert (r.status_code, r.json()["status"]) == (200, "en_comercio")


def test_la_llegada_cuenta_desde_la_calle_mas_cercana_al_comercio(cliente, sesion):
    """El comercio puede quedar adentro de una manzana: se mide hasta la calle más cercana."""
    pedido_id, rep = pedido_con_repartidor(sesion, "asignado", LAT + 0.0009, LON)   # a ≈ 100 m del comercio
    calle = (LAT + 0.0009, LON)   # ...pero esa es justo la calle más cercana al comercio
    usar_router(RouterFalso(ajustar=lambda p: (calle, 100.0) if abs(p[0] - LAT) < 1e-6 else (p, 0.0)))
    assert accion(cliente, rep, pedido_id, "arrived").status_code == 200


# ---------------------------------------------------------------- retirar
def test_no_se_retira_sin_haber_llegado(cliente, sesion):
    pedido_id, rep = pedido_con_repartidor(sesion, "asignado", LAT, LON)
    r = accion(cliente, rep, pedido_id, "picked-up")
    assert (r.status_code, r.json()["estado_actual"]) == (409, "asignado")


def test_se_retira_despues_de_llegar(cliente, sesion):
    pedido_id, rep = pedido_con_repartidor(sesion, "en_comercio", LAT, LON)
    r = accion(cliente, rep, pedido_id, "picked-up")
    assert (r.status_code, r.json()["status"]) == (200, "en_camino")


# ---------------------------------------------------------------- entregar
def test_no_se_puede_entregar_lejos_del_cliente(cliente, sesion):
    pedido_id, rep = pedido_con_repartidor(sesion, "en_camino", LAT, LON)   # sigue en el comercio, a ≈ 920 m del cliente
    r = accion(cliente, rep, pedido_id, "delivered")
    assert r.status_code == 409 and "del cliente" in r.json()["detail"]
    assert sesion.get(Order, pedido_id).status == "en_camino"


def test_cerca_del_cliente_se_entrega_y_el_repartidor_queda_libre(cliente, sesion):
    pedido_id, rep = pedido_con_repartidor(sesion, "en_camino", DEST_LAT + 0.0001, DEST_LON)
    r = accion(cliente, rep, pedido_id, "delivered")
    assert (r.status_code, r.json()["status"]) == (200, "entregado")
    sesion.expire_all()
    assert sesion.get(Courier, rep.id).status == "available"


# ---------------------------------------------------------------- cobros
def entregar(cliente, sesion):
    pedido_id, rep = pedido_con_repartidor(sesion, "en_camino", DEST_LAT, DEST_LON)
    assert accion(cliente, rep, pedido_id, "delivered").status_code == 200
    sesion.expire_all()
    return pedido_id, rep


def test_al_entregar_se_cobra_al_cliente_y_se_paga_al_comercio_y_al_repartidor(cliente, sesion):
    pedido_id, rep = entregar(cliente, sesion)
    pedido = sesion.get(Order, pedido_id)
    comercio_user = sesion.get(Merchant, pedido.merchant_id).user_id
    por_concepto = {e.concept: e for e in sesion.scalars(select(LedgerEntry).where(LedgerEntry.order_id == pedido_id))}
    assert por_concepto["cobro_cliente"].amount_cents == -16000 and por_concepto["cobro_cliente"].user_id == pedido.customer_user_id
    assert por_concepto["pago_comercio"].amount_cents == 9000 and por_concepto["pago_comercio"].user_id == comercio_user   # 90 % de $100
    assert por_concepto["pago_repartidor"].amount_cents == 11500 and por_concepto["pago_repartidor"].user_id == rep.user_id
    assert por_concepto["plataforma"].user_id is None and por_concepto["plataforma"].amount_cents == 16000 - 9000 - 11500


def test_los_asientos_de_un_pedido_suman_cero(cliente, sesion):
    pedido_id, _ = entregar(cliente, sesion)
    assert sesion.scalar(select(func.sum(LedgerEntry.amount_cents)).where(LedgerEntry.order_id == pedido_id)) == 0


def test_un_pedido_no_entregado_no_genera_cobros(cliente, sesion):
    pedido_con_repartidor(sesion, "en_comercio", LAT, LON)
    assert sesion.scalar(select(func.count()).select_from(LedgerEntry)) == 0


def test_el_saldo_de_cada_uno_refleja_el_pedido(cliente, sesion):
    pedido_id, rep = entregar(cliente, sesion)
    pedido = sesion.get(Order, pedido_id)
    comercio_user = sesion.get(Merchant, pedido.merchant_id).user_id
    for usuario, esperado in ((pedido.customer_user_id, -16000), (comercio_user, 9000), (rep.user_id, 11500)):
        r = cliente.get("/wallet", headers=cabecera(usuario))
        assert r.status_code == 200
        assert (r.json()["balance_cents"], r.json()["today_cents"]) == (esperado, esperado)
        assert r.json()["movements"][0]["order_id"] == str(pedido_id)
    assert cliente.get("/wallet").status_code == 401


def test_cada_uno_ve_solo_sus_movimientos(cliente, sesion):
    pedido_id, rep = entregar(cliente, sesion)
    otro = crear_pedido(sesion)
    cliente_ajeno = sesion.get(Order, otro).customer_user_id
    assert cliente.get("/wallet", headers=cabecera(cliente_ajeno)).json()["movements"] == []


# ---------------------------------------------------------------- pago al repartidor
def test_el_pago_incluye_el_viaje_hasta_el_comercio():
    solo_entrega = calcular_pago_repartidor(distancia_retiro_m=0, distancia_entrega_m=3000)
    con_retiro = calcular_pago_repartidor(distancia_retiro_m=4000, distancia_entrega_m=3000)
    assert solo_entrega == 4000 + 4500            # base $40 + 3 km × $15
    assert con_retiro == 4000 + 10500             # base + 7 km × $15: se paga el viaje al comercio
    assert con_retiro > solo_entrega


def test_el_pago_se_redondea_al_peso():
    assert calcular_pago_repartidor(1234, 567) % 100 == 0


def test_la_oferta_muestra_cuanto_cobraria_el_repartidor(cliente, sesion):
    pedido_id = crear_pedido(sesion, "listo")
    rep = repartidor_en(sesion, LAT + 0.0045, LON)   # a ≈ 500 m del comercio
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    (o,) = cliente.get("/courier/offers", headers=cabecera(rep.user_id)).json()
    assert 480 <= o["pickup_m"] <= 520 and 900 <= o["delivery_m"] <= 940
    assert o["pay_cents"] == calcular_pago_repartidor(o["pickup_m"], o["delivery_m"])


def test_al_aceptar_el_pago_queda_fijado_en_el_pedido(cliente, sesion):
    pedido_id = crear_pedido(sesion, "listo")
    rep = repartidor_en(sesion, LAT + 0.0045, LON)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    (o,) = cliente.get("/courier/offers", headers=cabecera(rep.user_id)).json()
    assert cliente.post(f"/courier/offers/{oferta.id}/accept", headers=cabecera(rep.user_id)).status_code == 200
    sesion.expire_all()
    assert sesion.get(Order, pedido_id).courier_pay_cents == o["pay_cents"]


# ---------------------------------------------------------------- conducir hacia el destino (demo)
def test_el_piloto_automatico_se_activa_y_se_apaga(cliente, sesion, redis_test):
    rep = repartidor_en(sesion, LAT, LON)
    assert cliente.post("/courier/autopilot", json={"activo": True}, headers=cabecera(rep.user_id)).status_code == 204
    assert redis_test.exists(f"autopilot:{rep.id}")
    cliente.post("/courier/autopilot", json={"activo": False}, headers=cabecera(rep.user_id))
    assert not redis_test.exists(f"autopilot:{rep.id}")


def test_con_el_piloto_automatico_la_moto_va_al_comercio_y_se_detiene_al_llegar(sesion, redis_test):
    import random

    from app.simulator.engine import Config, tick

    pedido_id, rep = pedido_con_repartidor(sesion, "asignado", LAT + 0.0135, LON)   # a ≈ 1,5 km
    redis_test.set(f"autopilot:{rep.id}", "1", ex=600)
    cfg = Config(velocidad_ms=100.0, generar_pedidos=False, demora_oferta_s=(0, 0), demora_comercio_s=(0, 0))
    for _ in range(12):
        tick(sesion, redis_test, cfg=cfg, rng=random.Random(1))
    from geoalchemy2 import Geometry
    from sqlalchemy import cast

    sesion.expire_all()
    g = cast(Courier.last_location, Geometry)
    lat, lon = sesion.execute(select(func.ST_Y(g), func.ST_X(g)).where(Courier.id == rep.id)).one()
    assert abs(lat - LAT) < 1e-4 and abs(lon - LON) < 1e-4          # llegó al comercio
    assert sesion.get(Order, pedido_id).status == "asignado"          # pero NO marcó nada: eso lo hace la persona con el botón


def test_sin_piloto_automatico_la_moto_humana_no_se_mueve(sesion, redis_test):
    import random

    from app.simulator.engine import Config, tick

    pedido_id, rep = pedido_con_repartidor(sesion, "asignado", LAT + 0.0135, LON)
    cfg = Config(velocidad_ms=100.0, generar_pedidos=False)
    tick(sesion, redis_test, cfg=cfg, rng=random.Random(1))
    from geoalchemy2 import Geometry
    from sqlalchemy import cast

    sesion.expire_all()
    g = cast(Courier.last_location, Geometry)
    assert sesion.execute(select(func.ST_Y(g)).where(Courier.id == rep.id)).scalar_one() == pytest.approx(LAT + 0.0135)
