"""Genera los estilos del mapa (claro y oscuro) a partir de UNA paleta.

Uso:  python3 map/construir_estilo.py     ->  web/map/style-claro.json y style-oscuro.json

Principios de diseño (docs/UXUI.md, sección 3): menos es más. Pocas etiquetas, paleta suave,
calles finas y jerarquizadas, y que lo único con color fuerte sea nuestra capa (repartidores,
ruta, destino), no el mapa base.

Los datos son de Protomaps/OpenStreetMap (ODbL): la atribución «© OpenStreetMap» es obligatoria.
"""
import json
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "web" / "map"
ATRIBUCION = '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a>'

PALETAS = {
    "claro": dict(
        tierra="#F4F3F0", agua="#CFE0EA", parque="#DFE9D8", arena="#EFEADF", edificio="#E9E7E2",
        calle="#FFFFFF", borde="#DAD8D3", avenida="#FFFFFF", borde_avenida="#CFCCC6",
        texto="#55595C", texto_suave="#8A8E90", halo="#FFFFFF", texto_agua="#6F95A8",
    ),
    "oscuro": dict(
        tierra="#1A1D21", agua="#0F2733", parque="#1E2D27", arena="#252622", edificio="#22262B",
        calle="#2C3138", borde="#1A1D21", avenida="#383F48", borde_avenida="#1A1D21",
        texto="#B2B8BD", texto_suave="#7C848B", halo="#1A1D21", texto_agua="#5C8AA0",
    ),
}

NOMBRE = ["coalesce", ["get", "name:es"], ["get", "name"]]
SIN_TUNEL = ["!=", ["get", "is_tunnel"], True]


def ancho(*pares):
    """Ancho de línea que crece con el zoom: ancho(z1, px1, z2, px2, ...)."""
    expresion = ["interpolate", ["exponential", 1.5], ["zoom"]]
    for zoom, px in pares:
        expresion += [zoom, px]
    return expresion


def estilo(tema: str) -> dict:
    p = PALETAS[tema]
    capas = [
        {"id": "fondo", "type": "background", "paint": {"background-color": p["tierra"]}},
        {"id": "parques", "type": "fill", "source": "montevideo", "source-layer": "landuse",
         "filter": ["in", ["get", "kind"], ["literal", ["park", "grass", "forest", "wood", "wetland",
                                                       "recreation_ground", "pitch", "nature_reserve", "garden"]]],
         "paint": {"fill-color": p["parque"]}},
        {"id": "arena", "type": "fill", "source": "montevideo", "source-layer": "landuse",
         "filter": ["==", ["get", "kind"], "beach"], "paint": {"fill-color": p["arena"]}},
        {"id": "agua", "type": "fill", "source": "montevideo", "source-layer": "water",
         "filter": ["==", ["geometry-type"], "Polygon"], "paint": {"fill-color": p["agua"]}},
        {"id": "rios", "type": "line", "source": "montevideo", "source-layer": "water",
         "filter": ["==", ["geometry-type"], "LineString"],
         "paint": {"line-color": p["agua"], "line-width": ancho((10, 0.5), (16, 3))}},
        {"id": "edificios", "type": "fill", "source": "montevideo", "source-layer": "buildings", "minzoom": 14,
         "paint": {"fill-color": p["edificio"], "fill-opacity": ["interpolate", ["linear"], ["zoom"], 14, 0, 15, 1]}},
        # Sendas: solo al acercarse mucho
        {"id": "sendas", "type": "line", "source": "montevideo", "source-layer": "roads", "minzoom": 15,
         "filter": ["all", ["==", ["get", "kind"], "path"], SIN_TUNEL],
         "paint": {"line-color": p["borde"], "line-width": 1, "line-dasharray": [2, 2]}},
        # Calles chicas: finas, con borde
        {"id": "calles-borde", "type": "line", "source": "montevideo", "source-layer": "roads", "minzoom": 12,
         "filter": ["all", ["==", ["get", "kind"], "minor_road"], SIN_TUNEL],
         "layout": {"line-cap": "round", "line-join": "round"},
         "paint": {"line-color": p["borde"], "line-width": ancho((12, 0.6), (15, 3.2), (18, 14))}},
        {"id": "calles", "type": "line", "source": "montevideo", "source-layer": "roads", "minzoom": 12,
         "filter": ["all", ["==", ["get", "kind"], "minor_road"], SIN_TUNEL],
         "layout": {"line-cap": "round", "line-join": "round"},
         "paint": {"line-color": p["calle"], "line-width": ancho((12, 0.3), (15, 2.2), (18, 12))}},
        # Avenidas: más gruesas que las calles (jerarquía)
        {"id": "avenidas-borde", "type": "line", "source": "montevideo", "source-layer": "roads", "minzoom": 7,
         "filter": ["all", ["in", ["get", "kind"], ["literal", ["major_road", "medium_road", "highway"]]], SIN_TUNEL],
         "layout": {"line-cap": "round", "line-join": "round"},
         "paint": {"line-color": p["borde_avenida"], "line-width": ancho((7, 0.4), (12, 1.6), (15, 5.5), (18, 22))}},
        {"id": "avenidas", "type": "line", "source": "montevideo", "source-layer": "roads", "minzoom": 7,
         "filter": ["all", ["in", ["get", "kind"], ["literal", ["major_road", "medium_road", "highway"]]], SIN_TUNEL],
         "layout": {"line-cap": "round", "line-join": "round"},
         "paint": {"line-color": p["avenida"], "line-width": ancho((7, 0.25), (12, 1.1), (15, 4), (18, 19))}},
        # Etiquetas: pocas y suaves
        {"id": "etiqueta-agua", "type": "symbol", "source": "montevideo", "source-layer": "water", "minzoom": 8,
         "filter": ["all", ["has", "name"], ["in", ["get", "kind"], ["literal", ["ocean", "sea", "bay", "lake"]]]],
         "layout": {"text-field": NOMBRE, "text-font": ["Noto Sans Italic"], "text-size": 13,
                    "text-letter-spacing": 0.15},
         "paint": {"text-color": p["texto_agua"], "text-halo-color": p["agua"], "text-halo-width": 1}},
        {"id": "etiqueta-calles", "type": "symbol", "source": "montevideo", "source-layer": "roads", "minzoom": 14,
         "filter": ["all", ["has", "name"], ["in", ["get", "kind"], ["literal", ["major_road", "highway"]]]],
         "layout": {"symbol-placement": "line", "text-field": NOMBRE, "text-font": ["Noto Sans Regular"],
                    "text-size": ["interpolate", ["linear"], ["zoom"], 14, 10, 18, 13]},
         "paint": {"text-color": p["texto"], "text-halo-color": p["halo"], "text-halo-width": 1.5}},
        {"id": "etiqueta-barrios", "type": "symbol", "source": "montevideo", "source-layer": "places", "minzoom": 12,
         "filter": ["==", ["get", "kind"], "neighbourhood"],
         "layout": {"text-field": ["upcase", NOMBRE], "text-font": ["Noto Sans Medium"], "text-size": 10.5,
                    "text-letter-spacing": 0.12, "text-max-width": 7},
         "paint": {"text-color": p["texto_suave"], "text-halo-color": p["halo"], "text-halo-width": 1.5}},
        {"id": "etiqueta-ciudades", "type": "symbol", "source": "montevideo", "source-layer": "places",
         "filter": ["==", ["get", "kind"], "locality"],
         "layout": {"text-field": NOMBRE, "text-font": ["Noto Sans Medium"],
                    "text-size": ["interpolate", ["linear"], ["zoom"], 6, 11, 12, 17], "text-max-width": 8},
         "paint": {"text-color": p["texto"], "text-halo-color": p["halo"], "text-halo-width": 2}},
    ]
    return {
        "version": 8,
        "name": f"Cadete · {tema}",
        "glyphs": "__ORIGEN__/map/fonts/{fontstack}/{range}.pbf",   # __ORIGEN__ lo reemplaza mapa.js
        "sources": {"montevideo": {
            "type": "vector", "url": "pmtiles://__ORIGEN__/map/montevideo.pmtiles",
            "attribution": ATRIBUCION, "minzoom": 0, "maxzoom": 15,
        }},
        "layers": capas,
    }


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for tema in PALETAS:
        archivo = DESTINO / f"style-{tema}.json"
        archivo.write_text(json.dumps(estilo(tema), ensure_ascii=False, indent=1) + "\n")
        print("escrito", archivo.relative_to(DESTINO.parent.parent))
