import json
from datetime import datetime, timedelta, timezone

from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select

from app.models import Courier, CourierPosition
from app.services.couriers import purgar_posiciones_antiguas
from tests.helpers import cabecera, crear_cliente, crear_repartidor, punto


def enviar(cliente, repartidor, lat, lon):
    return cliente.post("/courier/location", json={"lat": lat, "lon": lon}, headers=cabecera(repartidor.user_id))


def donde_esta(sesion, repartidor_id):
    sesion.expire_all()
    geom = cast(Courier.last_location, Geometry)
    return sesion.execute(select(func.ST_Y(geom), func.ST_X(geom)).where(Courier.id == repartidor_id)).one()


def test_enviar_posicion_actualiza_todo(cliente, sesion, redis_test):
    rep = crear_repartidor(sesion)
    assert enviar(cliente, rep, -34.91, -56.15).status_code == 204
    assert donde_esta(sesion, rep.id) == (-34.91, -56.15)
    assert sesion.get(Courier, rep.id).last_seen_at is not None
    historial = sesion.scalars(select(CourierPosition).where(CourierPosition.courier_id == rep.id)).all()
    assert len(historial) == 1
    actual = json.loads(redis_test.get(f"courier:{rep.id}:pos"))
    assert (actual["lat"], actual["lon"]) == (-34.91, -56.15)


def test_cada_posicion_nueva_se_suma_al_historial_y_pisa_la_actual(cliente, sesion):
    rep = crear_repartidor(sesion)
    enviar(cliente, rep, -34.91, -56.15)
    enviar(cliente, rep, -34.92, -56.16)
    assert donde_esta(sesion, rep.id) == (-34.92, -56.16)
    assert len(sesion.scalars(select(CourierPosition)).all()) == 2


def test_solo_los_repartidores_envian_posicion(cliente, sesion):
    yo = crear_cliente(sesion)
    r = cliente.post("/courier/location", json={"lat": -34.9, "lon": -56.1}, headers=cabecera(yo.id))
    assert r.status_code == 403


def test_coordenadas_imposibles_dan_422(cliente, sesion):
    rep = crear_repartidor(sesion)
    assert enviar(cliente, rep, 91, -56.15).status_code == 422
    assert enviar(cliente, rep, -34.9, 181).status_code == 422


def test_sin_sesion_no_se_envia_posicion(cliente):
    assert cliente.post("/courier/location", json={"lat": -34.9, "lon": -56.1}).status_code == 401


def test_el_repartidor_se_pone_disponible_y_desconectado(cliente, sesion):
    rep = crear_repartidor(sesion)
    r = cliente.post("/courier/status", json={"status": "available"}, headers=cabecera(rep.user_id))
    assert (r.status_code, r.json()["status"]) == (200, "available")
    cliente.post("/courier/status", json={"status": "offline"}, headers=cabecera(rep.user_id))
    sesion.expire_all()
    assert sesion.get(Courier, rep.id).status == "offline"


def test_un_repartidor_ocupado_no_cambia_su_estado(cliente, sesion):
    rep = crear_repartidor(sesion)
    rep.status = "busy"
    sesion.commit()
    r = cliente.post("/courier/status", json={"status": "available"}, headers=cabecera(rep.user_id))
    assert r.status_code == 409


def test_estado_inventado_da_422(cliente, sesion):
    rep = crear_repartidor(sesion)
    r = cliente.post("/courier/status", json={"status": "busy"}, headers=cabecera(rep.user_id))
    assert r.status_code == 422


def test_se_purgan_las_posiciones_de_mas_de_7_dias(sesion):
    rep = crear_repartidor(sesion)
    ahora = datetime.now(timezone.utc)
    for dias in (10, 8, 6, 0):
        sesion.add(CourierPosition(courier_id=rep.id, location=punto(), recorded_at=ahora - timedelta(days=dias)))
    sesion.commit()
    borradas = purgar_posiciones_antiguas(sesion, dias=7)
    assert borradas == 2
    assert len(sesion.scalars(select(CourierPosition)).all()) == 2
