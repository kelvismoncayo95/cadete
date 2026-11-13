import httpx
import pytest

from app.services.geo import distancia_m, punto_a_distancia
from app.services.routing import ConRespaldo, OsrmRouter, RectaRouter, Ruta

A = (-34.9115, -56.1495)   # Pocitos
B = (-34.9040, -56.1790)   # Cordón


# ---------------------------------------------------------------- recorrer una polilínea
CALLES = [(-34.900, -56.150), (-34.900, -56.140), (-34.890, -56.140)]   # va al este y después al norte


def test_punto_a_distancia_avanza_por_la_polilinea_y_dobla_en_las_esquinas():
    tramo1 = distancia_m(*CALLES[0], *CALLES[1])
    lat, lon, llego = punto_a_distancia(CALLES, tramo1 / 2)
    assert (round(lat, 4), llego) == (-34.9, False) and CALLES[0][1] < lon < CALLES[1][1]
    lat, lon, llego = punto_a_distancia(CALLES, tramo1 + 100)   # pasó la esquina: ahora sube por la otra calle
    assert round(lon, 4) == -56.14 and lat > -34.9 and not llego


def test_punto_a_distancia_llega_al_final_si_alcanza():
    total = distancia_m(*CALLES[0], *CALLES[1]) + distancia_m(*CALLES[1], *CALLES[2])
    assert punto_a_distancia(CALLES, total + 50) == (*CALLES[2], True)
    assert punto_a_distancia(CALLES, total - 50)[2] is False


def test_punto_a_distancia_con_un_solo_punto():
    assert punto_a_distancia([CALLES[0]], 10) == (*CALLES[0], True)


# ---------------------------------------------------------------- respaldo en línea recta
def test_el_respaldo_en_recta_mide_en_linea_recta():
    r = RectaRouter(velocidad_kmh=30).ruta([A, B])
    assert r.coordenadas == [A, B]
    assert r.distancia_m == pytest.approx(distancia_m(*A, *B))
    assert r.duracion_s == pytest.approx(r.distancia_m / (30 / 3.6), rel=0.01)


def test_la_ruta_recta_con_varias_paradas_suma_los_tramos():
    r = RectaRouter().ruta([A, B, A])
    assert len(r.coordenadas) == 3 and r.distancia_m == pytest.approx(2 * distancia_m(*A, *B))


def test_la_tabla_recta_da_una_fila_por_origen():
    tabla = RectaRouter().tabla([A, B], B)
    assert tabla[1] == (0.0, 0.0) and tabla[0][1] == pytest.approx(distancia_m(*A, *B))


def test_ajustar_en_recta_no_mueve_el_punto():
    assert RectaRouter().ajustar(A) == (A, 0.0)


# ---------------------------------------------------------------- cliente de OSRM (con un servidor falso)
def osrm_falso(manejador) -> OsrmRouter:
    return OsrmRouter("http://osrm.test", cliente=httpx.Client(transport=httpx.MockTransport(manejador), base_url="http://osrm.test"))


def test_osrm_ruta_pide_lon_lat_y_entrega_lat_lon():
    pedidos = []

    def manejador(req: httpx.Request):
        pedidos.append(str(req.url))
        return httpx.Response(200, json={"code": "Ok", "routes": [{
            "distance": 3451.2, "duration": 391.0,
            "geometry": {"coordinates": [[-56.1495, -34.9115], [-56.16, -34.91], [-56.179, -34.904]]}}]})

    r = osrm_falso(manejador).ruta([A, B])
    assert "/route/v1/driving/-56.1495,-34.9115;-56.179,-34.904" in pedidos[0]
    assert r == Ruta(3451.2, 391.0, [(-34.9115, -56.1495), (-34.91, -56.16), (-34.904, -56.179)])


def test_osrm_tabla_devuelve_duracion_y_distancia_de_cada_origen_y_none_si_no_hay_camino():
    def manejador(req):
        assert "sources=0;1" in str(req.url) and "destinations=2" in str(req.url)
        return httpx.Response(200, json={"code": "Ok", "durations": [[120.5], [None]], "distances": [[900.0], [None]]})

    assert osrm_falso(manejador).tabla([A, B], A) == [(120.5, 900.0), None]


def test_osrm_ajustar_devuelve_el_punto_de_la_calle_y_la_distancia():
    def manejador(req):
        return httpx.Response(200, json={"code": "Ok", "waypoints": [{"location": [-56.15, -34.91], "distance": 42.5}]})

    assert osrm_falso(manejador).ajustar(A) == ((-34.91, -56.15), 42.5)


@pytest.mark.parametrize("respuesta", [
    lambda req: httpx.Response(500),
    lambda req: httpx.Response(200, json={"code": "NoRoute"}),
    lambda req: (_ for _ in ()).throw(httpx.ConnectError("sin red")),
])
def test_osrm_devuelve_none_si_falla(respuesta):
    r = osrm_falso(respuesta)
    assert r.ruta([A, B]) is None and r.tabla([A], B) is None and r.ajustar(A) is None


def test_el_respaldo_usa_la_recta_cuando_osrm_no_responde_y_lo_avisa():
    caido = osrm_falso(lambda req: httpx.Response(500))
    router = ConRespaldo(caido, RectaRouter())
    assert router.ruta([A, B]).coordenadas == [A, B]
    assert router.tabla([A], B)[0][1] == pytest.approx(distancia_m(*A, *B))
    assert router.ajustar(A) == (A, 0.0)
    assert router.usando_respaldo is True


def test_el_respaldo_no_se_usa_si_osrm_responde():
    bien = osrm_falso(lambda req: httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 1.0, "duration": 1.0, "geometry": {"coordinates": [[-56.1, -34.9], [-56.2, -34.8]]}}]}))
    router = ConRespaldo(bien, RectaRouter())
    router.ruta([A, B])
    assert router.usando_respaldo is False


# ---------------------------------------------------------------- contra el OSRM REAL (se salta si no está corriendo)
def _osrm_real():
    from app.core.config import settings

    try:
        httpx.get(f"{settings.osrm_url}/nearest/v1/driving/-56.15,-34.91", timeout=1.5).raise_for_status()
    except Exception:
        pytest.skip("OSRM no está corriendo (docker compose up -d osrm)")
    return OsrmRouter(settings.osrm_url)


def test_real_la_ruta_por_calles_es_mas_larga_que_la_recta_y_sigue_las_calles():
    osrm = _osrm_real()
    r = osrm.ruta([A, B])
    assert r.distancia_m > distancia_m(*A, *B) * 1.05
    assert len(r.coordenadas) > 10   # una polilínea con las esquinas, no una recta


def test_real_respeta_los_sentidos_unicos_ida_y_vuelta_no_son_iguales():
    osrm = _osrm_real()
    ida, vuelta = osrm.ruta([A, B]), osrm.ruta([B, A])
    assert ida.distancia_m != pytest.approx(vuelta.distancia_m, abs=1.0)


def test_real_un_punto_en_el_rio_esta_lejos_de_cualquier_calle():
    osrm = _osrm_real()
    _, metros = osrm.ajustar((-34.96, -56.15))   # en pleno Río de la Plata
    assert metros > 1000
    _, metros = osrm.ajustar((-34.9065, -56.1995))   # Plaza Independencia
    assert metros < 100


def test_real_la_tabla_de_duraciones_funciona_con_varios_origenes():
    osrm = _osrm_real()
    tabla = osrm.tabla([A, (-34.9230, -56.1580), (-34.96, -56.15)], B)   # el último origen está en el río
    assert tabla is not None and len(tabla) == 3
    assert tabla[0][0] > 0 and tabla[0][1] > distancia_m(*A, *B)
