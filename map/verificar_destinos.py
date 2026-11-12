"""Comprueba que los destinos y comercios de la demo caen en TIERRA FIRME (no en agua).

Lee la tesela de cada punto del archivo PMTiles y mira si el punto está dentro de un polígono de agua.
Requiere:  pip install mapbox-vector-tile shapely   (en un entorno aparte; no es parte de la app)
Uso:       python3 map/verificar_destinos.py            (desde la raíz del proyecto)
"""
import gzip
import math
import subprocess
import sys
from pathlib import Path

import mapbox_vector_tile as mvt
from shapely.geometry import Point, shape
from shapely.ops import unary_union

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
Z = 15
AGUA = {"ocean", "sea", "bay", "water", "lake", "river"}
_cache: dict = {}


def _tesela(lat: float, lon: float):
    n = 2**Z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def en_agua(lat: float, lon: float) -> bool:
    x, y = _tesela(lat, lon)
    tx, ty = int(x), int(y)
    if (tx, ty) not in _cache:
        crudo = subprocess.run(
            [str(RAIZ / "map/bin/pmtiles"), "tile", str(RAIZ / "web/map/montevideo.pmtiles"), str(Z), str(tx), str(ty)],
            capture_output=True).stdout
        try:
            crudo = gzip.decompress(crudo)
        except Exception:
            pass
        datos = mvt.decode(crudo, default_options={"y_coord_down": True}) if crudo else {}
        poligonos = [shape(f["geometry"]) for f in datos.get("water", {}).get("features", [])
                     if f["geometry"]["type"] in ("Polygon", "MultiPolygon") and f["properties"].get("kind") in AGUA]
        _cache[(tx, ty)] = (unary_union(poligonos) if poligonos else None, datos["water"]["extent"] if "water" in datos else 4096)
    union, extension = _cache[(tx, ty)]
    return bool(union is not None and union.contains(Point((x - tx) * extension, (y - ty) * extension)))


def _lista(archivo: str, nombre: str) -> list:
    """Lee una lista literal (DESTINOS, COMERCIOS) del código sin importarlo: así no hacen falta las
    dependencias de la app (base de datos, Redis) en este entorno aparte."""
    import ast

    texto = (RAIZ / archivo).read_text()
    inicio = texto.index(f"{nombre} = [") + len(f"{nombre} = ")
    fin = texto.index("\n]\n", inicio) + 2
    return ast.literal_eval(texto[inicio:fin])


if __name__ == "__main__":
    puntos = [(n, a, o) for n, a, o in _lista("app/services/demo.py", "DESTINOS")]
    puntos += [(c["name"], c["lat"], c["lon"]) for c in _lista("app/seed.py", "COMERCIOS")]
    malos = [n for n, a, o in puntos if en_agua(a, o)]
    for n, a, o in puntos:
        print(f"{n:34} {'** EN AGUA **' if n in malos else 'tierra'}")
    sys.exit(1 if malos else 0)
