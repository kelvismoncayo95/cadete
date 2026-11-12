"""El repartidor más cercano. El comercio está en (lat -34.90, lon -56.15).

Un grado de latitud son ~111,2 km, así que:
  0,0045° ≈ 500 m · 0,0135° ≈ 1,5 km · 0,0432° ≈ 4,8 km · 0,0495° ≈ 5,5 km · 0,054° ≈ 6 km
"""
from sqlalchemy.orm import Session

from app.services.couriers import buscar_repartidor_mas_cercano
from tests.helpers import crear_comercio, repartidor_en

LAT, LON = -34.90, -56.15


def al_norte(grados: float) -> tuple[float, float]:
    return LAT + grados, LON


def test_elige_al_mas_cercano_sin_importar_el_orden_de_creacion(sesion):
    comercio, _ = crear_comercio(sesion)
    lejos = repartidor_en(sesion, *al_norte(0.0135))
    cerca = repartidor_en(sesion, *al_norte(0.0045))
    medio = repartidor_en(sesion, *al_norte(0.0090))
    elegido = buscar_repartidor_mas_cercano(sesion, comercio.id)
    assert elegido is not None
    assert elegido.courier.id == cerca.id
    assert lejos.id != elegido.courier.id and medio.id != elegido.courier.id


def test_devuelve_la_distancia_en_metros(sesion):
    comercio, _ = crear_comercio(sesion)
    repartidor_en(sesion, *al_norte(0.0045))
    elegido = buscar_repartidor_mas_cercano(sesion, comercio.id)
    assert 480 <= elegido.distancia_m <= 520


def test_respeta_el_radio_de_5_km(sesion):
    comercio, _ = crear_comercio(sesion)
    adentro = repartidor_en(sesion, *al_norte(0.0432))
    repartidor_en(sesion, *al_norte(0.0495))
    assert buscar_repartidor_mas_cercano(sesion, comercio.id).courier.id == adentro.id
    sesion.query(type(adentro)).filter_by(id=adentro.id).update({"status": "offline"})
    sesion.commit()
    assert buscar_repartidor_mas_cercano(sesion, comercio.id) is None


def test_sin_repartidores_devuelve_none(sesion):
    comercio, _ = crear_comercio(sesion)
    assert buscar_repartidor_mas_cercano(sesion, comercio.id) is None


def test_ignora_a_los_que_no_estan_disponibles(sesion):
    comercio, _ = crear_comercio(sesion)
    repartidor_en(sesion, *al_norte(0.0010), estado="offline")
    repartidor_en(sesion, *al_norte(0.0020), estado="busy")
    libre = repartidor_en(sesion, *al_norte(0.0200))
    assert buscar_repartidor_mas_cercano(sesion, comercio.id).courier.id == libre.id


def test_ignora_a_los_que_no_tienen_posicion(sesion):
    from tests.helpers import crear_repartidor

    comercio, _ = crear_comercio(sesion)
    sin_posicion = crear_repartidor(sesion)
    sin_posicion.status = "available"
    sesion.commit()
    assert buscar_repartidor_mas_cercano(sesion, comercio.id) is None


def test_puede_excluir_a_los_que_ya_rechazaron(sesion):
    comercio, _ = crear_comercio(sesion)
    cerca = repartidor_en(sesion, *al_norte(0.0045))
    lejos = repartidor_en(sesion, *al_norte(0.0135))
    elegido = buscar_repartidor_mas_cercano(sesion, comercio.id, excluir=[cerca.id])
    assert elegido.courier.id == lejos.id


def test_dos_pedidos_a_la_vez_no_reciben_al_mismo_repartidor(migrada, sesion):
    """SKIP LOCKED: si alguien ya está eligiendo a un repartidor, el otro pedido pasa al siguiente."""
    comercio, _ = crear_comercio(sesion)
    cerca = repartidor_en(sesion, *al_norte(0.0045))
    lejos = repartidor_en(sesion, *al_norte(0.0135))
    with Session(migrada) as a, Session(migrada) as b:
        primero = buscar_repartidor_mas_cercano(a, comercio.id).courier.id    # a lo bloquea (sin commit)
        segundo = buscar_repartidor_mas_cercano(b, comercio.id).courier.id    # b no espera: toma al siguiente
        tercero = buscar_repartidor_mas_cercano(b, comercio.id).courier.id    # el de b sigue siendo suyo
        a.rollback()
        b.rollback()
    assert primero == cerca.id
    assert segundo == lejos.id
    assert tercero == lejos.id
