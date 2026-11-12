import math

from app.services.geo import distancia_m, minutos_estimados, mover_hacia


def test_un_grado_de_latitud_son_unos_111_km():
    assert 111_000 <= distancia_m(-34.0, -56.0, -35.0, -56.0) <= 111_400


def test_distancia_corta_conocida():
    assert 495 <= distancia_m(-34.90, -56.15, -34.8955, -56.15) <= 505


def test_distancia_a_si_mismo_es_cero():
    assert distancia_m(-34.9, -56.1, -34.9, -56.1) == 0


def test_mover_hacia_avanza_exactamente_los_metros_pedidos():
    lat, lon = mover_hacia(-34.90, -56.15, -34.80, -56.15, 300)
    assert math.isclose(distancia_m(-34.90, -56.15, lat, lon), 300, rel_tol=0.01)
    assert lat > -34.90  # va hacia el norte


def test_mover_hacia_no_se_pasa_del_destino():
    assert mover_hacia(-34.90, -56.15, -34.8995, -56.15, 1000) == (-34.8995, -56.15)


def test_minutos_estimados_a_20_kmh():
    assert minutos_estimados(5000, velocidad_kmh=20) == 15
    assert minutos_estimados(100, velocidad_kmh=20) == 1   # nunca 0: siempre se redondea hacia arriba
    assert minutos_estimados(0, velocidad_kmh=20) == 0
