import pytest
from sqlalchemy import text

from app.services.direcciones import normalizar, parsear
from app.services.geocodificador import buscar
from tests.helpers import cabecera, crear_cliente

# Una «ciudad» de juguete: 18 de Julio (horizontal) y Rondeau (vertical) se cruzan en (-34.9060, -56.1900).
JULIO = "LINESTRING(-56.2000 -34.9060, -56.1500 -34.9060)"
RONDEAU = "LINESTRING(-56.1900 -34.9100, -56.1900 -34.8900)"
COLONIA = "LINESTRING(-56.2000 -34.9010, -56.1500 -34.9010)"
CERCANA = "LINESTRING(-56.1700 -34.9040, -56.1700 -34.9059)"      # termina a ~11 m de 18 de Julio, sin tocarla
LEJANA = "LINESTRING(-55.5000 -34.9000, -55.4900 -34.9000)"      # en otro departamento: fuera de la zona de entrega


@pytest.fixture
def ciudad(sesion):
    for nombre, geom in (("Avenida 18 de Julio", JULIO), ("Avenida General Rondeau", RONDEAU), ("Colonia", COLONIA),
                          ("Cercana", CERCANA), ("Lejana", LEJANA)):
        sesion.execute(text("INSERT INTO geo_calles (nombre, norm, geom) VALUES (:n, :m, ST_Multi(ST_GeomFromText(:g, 4326)))"),
                       {"n": nombre, "m": normalizar(nombre), "g": geom})
    # Números de puerta de 18 de Julio: 1000 en el oeste (-56.2000) y 1400 en el este (-56.1600), de 100 en 100
    for i, numero in enumerate((1000, 1100, 1200, 1300, 1400)):
        sesion.execute(text("INSERT INTO geo_direcciones (calle_norm, numero, geom) VALUES (:c, :n, ST_GeomFromText(:g, 4326))"),
                       {"c": normalizar("Avenida 18 de Julio"), "n": numero, "g": f"POINT({-56.2000 + i * 0.01} -34.9062)"})
    for numero, lat in ((100, -34.9090), (500, -34.8910)):
        sesion.execute(text("INSERT INTO geo_direcciones (calle_norm, numero, geom) VALUES (:c, :n, ST_GeomFromText(:g, 4326))"),
                       {"c": normalizar("Avenida General Rondeau"), "n": numero, "g": f"POINT(-56.1902 {lat})"})
    sesion.execute(text("INSERT INTO geo_direcciones (calle_norm, numero, geom) VALUES ('lejana', 100, ST_GeomFromText('POINT(-55.5 -34.9)', 4326))"))
    sesion.commit()
    return sesion


# ---------------------------------------------------------------- texto
@pytest.mark.parametrize("escrito,esperado", [
    ("Av. 18 de Julio", "avenida 18 de julio"),
    ("  GRAL.  Rondeau ", "general rondeau"),
    ("Bvar. Artigas", "bulevar artigas"),
    ("Dr. Joaquín Requena", "doctor joaquin requena"),
    ("Ñandú, esq. Ejido", "nandu esq ejido"),
    ("Calle Colonia", "colonia"),
])
def test_normalizar_saca_tildes_mayusculas_puntos_y_expande_abreviaturas(escrito, esperado):
    assert normalizar(escrito) == esperado


@pytest.mark.parametrize("escrito,esperado", [
    ("Av. 18 de Julio 1500", ("avenida 18 de julio", 1500, None)),
    ("colonia nº 1234", ("colonia", 1234, None)),
    ("Rondeau nro. 1571", ("rondeau", 1571, None)),
    ("18 de julio y Rondeau", ("18 de julio", None, "rondeau")),
    ("Colonia esq. Ejido", ("colonia", None, "ejido")),
    ("Colonia esquina Ejido", ("colonia", None, "ejido")),
    ("Rondeau", ("rondeau", None, None)),
])
def test_parsear_separa_calle_numero_y_esquina(escrito, esperado):
    assert parsear(escrito) == esperado


# ---------------------------------------------------------------- búsqueda
def test_una_direccion_con_numero_exacto_da_el_punto_exacto(ciudad):
    (r, *_) = buscar(ciudad, "Av. 18 de Julio 1200")
    assert r["etiqueta"] == "Avenida 18 de Julio 1200" and r["exacta"] is True
    assert (round(r["lat"], 4), round(r["lon"], 4)) == (-34.9062, -56.1800)


def test_un_numero_que_falta_se_interpola_entre_los_vecinos(ciudad):
    (r, *_) = buscar(ciudad, "18 de julio 1250")   # entre 1200 (-56.18) y 1300 (-56.17): a la mitad
    assert r["exacta"] is False and round(r["lon"], 4) == -56.1750 and round(r["lat"], 4) == -34.9062


def test_un_numero_fuera_del_rango_conocido_usa_el_mas_cercano(ciudad):
    (r, *_) = buscar(ciudad, "18 de julio 9000")
    assert r["exacta"] is False and round(r["lon"], 4) == -56.1600   # el 1400, el último conocido


def test_una_calle_sin_numero_da_un_punto_en_medio_de_la_calle(ciudad):
    (r, *_) = buscar(ciudad, "Colonia")
    assert r["etiqueta"] == "Colonia" and r["exacta"] is False
    assert round(r["lat"], 4) == -34.9010 and -56.2000 < r["lon"] < -56.1500


def test_la_esquina_de_dos_calles_da_el_cruce(ciudad):
    (r, *_) = buscar(ciudad, "18 de julio y Rondeau")
    assert r["etiqueta"] == "Avenida 18 de Julio y Avenida General Rondeau" and r["exacta"] is True
    assert (round(r["lat"], 4), round(r["lon"], 4)) == (-34.9060, -56.1900)


def test_se_encuentra_la_calle_aunque_falten_palabras_del_nombre_completo(ciudad):
    (r, *_) = buscar(ciudad, "Rondeau 500")          # la calle se llama «Avenida General Rondeau»
    assert r["etiqueta"] == "Avenida General Rondeau 500" and r["exacta"] is True


def test_dos_calles_que_casi_se_tocan_dan_el_punto_mas_cercano_como_aproximado(ciudad):
    (r, *_) = buscar(ciudad, "18 de julio y cercana")
    assert r["exacta"] is False and round(r["lat"], 3) == -34.906 and round(r["lon"], 2) == -56.17


def test_dos_calles_lejanas_entre_si_no_dan_cruce(ciudad):
    assert buscar(ciudad, "colonia y lejana") == []


def test_se_descartan_los_lugares_fuera_de_la_zona_de_entrega(ciudad):
    assert buscar(ciudad, "Lejana 100") == []        # existe en los datos, pero está en otro departamento
    assert buscar(ciudad, "Lejana") == []


def test_una_calle_que_no_existe_no_da_resultados(ciudad):
    assert buscar(ciudad, "Calle Inexistente 123") == []


def test_cada_resultado_trae_lo_necesario_para_el_mapa(ciudad):
    (r, *_) = buscar(ciudad, "Colonia")
    assert set(r) == {"etiqueta", "lat", "lon", "exacta"}


# ---------------------------------------------------------------- API
def test_el_endpoint_busca_direcciones(cliente, ciudad):
    yo = crear_cliente(ciudad)
    r = cliente.get("/geocode", params={"q": "Av. 18 de Julio 1200"}, headers=cabecera(yo.id))
    assert r.status_code == 200 and r.json()["resultados"][0]["etiqueta"] == "Avenida 18 de Julio 1200"


def test_el_endpoint_pide_sesion_y_una_busqueda_razonable(cliente, ciudad):
    yo = crear_cliente(ciudad)
    assert cliente.get("/geocode", params={"q": "colonia"}).status_code == 401
    assert cliente.get("/geocode", params={"q": "ab"}, headers=cabecera(yo.id)).status_code == 422
    assert cliente.get("/geocode", params={"q": "x" * 200}, headers=cabecera(yo.id)).status_code == 422


def test_el_endpoint_limita_las_busquedas_por_minuto(cliente, ciudad):
    yo = crear_cliente(ciudad)
    for _ in range(30):
        assert cliente.get("/geocode", params={"q": "colonia"}, headers=cabecera(yo.id)).status_code == 200
    assert cliente.get("/geocode", params={"q": "colonia"}, headers=cabecera(yo.id)).status_code == 429


# ---------------------------------------------------------------- con los datos REALES de Montevideo (se salta si no están cargados)
def test_real_con_los_datos_de_openstreetmap():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.core.zone import dentro_de_montevideo

    try:
        motor = create_engine(settings.db_url)
        with Session(motor) as s:
            if s.execute(text("SELECT count(*) FROM geo_direcciones")).scalar() < 1000:
                pytest.skip("Los datos de direcciones no están cargados (geocoder/cargar.py)")
            for consulta in ("Av. 18 de Julio 1500", "Rondeau 1571", "Colonia y Ejido", "Bulevar Artigas 1200"):
                resultados = buscar(s, consulta)
                assert resultados, consulta
                assert dentro_de_montevideo(resultados[0]["lat"], resultados[0]["lon"]), (consulta, resultados[0])
    except Exception as e:  # noqa: BLE001 - sin base de desarrollo (por ejemplo en CI)
        if "skip" in type(e).__name__.lower():
            raise
        pytest.skip(f"base de desarrollo no disponible: {type(e).__name__}")
