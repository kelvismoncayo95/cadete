import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

WEB = Path(__file__).resolve().parent.parent / "web"
ESTILOS = ["claro", "oscuro"]


def estilo(nombre: str) -> dict:
    return json.loads((WEB / "map" / f"style-{nombre}.json").read_text())


@pytest.mark.parametrize("nombre", ESTILOS)
def test_el_estilo_es_valido_y_muestra_la_atribucion_de_openstreetmap(nombre):
    """La licencia de los datos (ODbL) EXIGE mostrar «© OpenStreetMap»."""
    e = estilo(nombre)
    assert e["version"] == 8
    fuente = e["sources"]["montevideo"]
    assert fuente["type"] == "vector" and fuente["url"].startswith("pmtiles://")
    assert "OpenStreetMap" in fuente["attribution"]


@pytest.mark.parametrize("nombre", ESTILOS)
def test_cada_capa_usa_una_capa_de_datos_que_existe(nombre):
    existentes = {"boundaries", "buildings", "earth", "landcover", "landuse", "places", "pois", "roads", "water"}
    for capa in estilo(nombre)["layers"]:
        if "source-layer" in capa:
            assert capa["source-layer"] in existentes, capa["id"]


@pytest.mark.parametrize("nombre", ESTILOS)
def test_las_tipografias_usadas_existen_en_el_proyecto(nombre):
    usadas = {f for c in estilo(nombre)["layers"] for f in c.get("layout", {}).get("text-font", [])}
    assert usadas, "el estilo debería tener etiquetas"
    for fuente in usadas:
        for rango in ("0-255", "256-511", "8192-8447"):
            assert (WEB / "map" / "fonts" / fuente / f"{rango}.pbf").is_file(), (fuente, rango)


def test_los_dos_temas_tienen_las_mismas_capas():
    assert [c["id"] for c in estilo("claro")["layers"]] == [c["id"] for c in estilo("oscuro")["layers"]]


def test_el_mapa_tiene_pocas_etiquetas():
    """Principio de diseño: menos es más. Las etiquetas son solo de barrios, ciudades, calles principales y agua."""
    etiquetas = [c["id"] for c in estilo("claro")["layers"] if c["type"] == "symbol"]
    assert 3 <= len(etiquetas) <= 6, etiquetas
    assert not any(c.get("source-layer") == "pois" for c in estilo("claro")["layers"])


def test_el_servidor_entrega_el_mapa_con_soporte_de_rangos():
    """PMTiles lee solo los pedacitos que necesita: el servidor tiene que soportar «Range»."""
    c = TestClient(app)
    r = c.get("/map/montevideo.pmtiles", headers={"Range": "bytes=0-126"})
    assert r.status_code == 206
    assert r.content[:7] == b"PMTiles"
    assert r.headers["content-range"].startswith("bytes 0-126/")


def test_el_servidor_entrega_el_estilo_y_la_pagina_del_mapa():
    c = TestClient(app)
    assert c.get("/map/style-claro.json").status_code == 200
    pagina = c.get("/mapa.html")
    assert pagina.status_code == 200 and "maplibre" in pagina.text.lower()
    assert c.get("/health").json() == {"status": "ok"}  # la API sigue funcionando junto a la web
