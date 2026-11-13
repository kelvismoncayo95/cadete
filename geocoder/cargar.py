"""Carga las calles y los números de puerta de OpenStreetMap en la base (tablas geo_calles y geo_direcciones).

Datos: el mismo archivo de Uruguay que usa el motor de rutas (routing/data/uruguay.osm.pbf, ver routing/preparar.sh).
Licencia: ODbL (© OpenStreetMap contributors).

Requisitos, en un entorno aparte (no son parte de la app):  pip install -r geocoder/requirements.txt
Uso:  python3 geocoder/cargar.py                  (usa DATABASE_URL o los datos de .env, base en localhost:5433)
      python3 geocoder/cargar.py otro.osm.pbf
"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import osmium
import psycopg

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from app.services.direcciones import normalizar  # noqa: E402  (solo usa la biblioteca estándar)

# Un poco más grande que la zona de entrega (Montevideo): así las calles de borde quedan completas.
LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -56.50, -35.00, -55.95, -34.70
GENERICOS = {"vehicular peatonal", "peatonal", "vehicular", "sin nombre"}


def dentro(lon: float, lat: float) -> bool:
    return LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX


class Lector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.fabrica = osmium.geom.WKTFactory()
        self.tramos: dict[str, list[str]] = defaultdict(list)   # nombre normalizado → tramos (WKT)
        self.nombres: dict[str, str] = {}                        # nombre normalizado → cómo se escribe
        self.puertas: list[tuple[str, int, float, float]] = []

    def way(self, w):
        t = w.tags
        if "highway" not in t or "name" not in t:
            return
        norm = normalizar(t["name"])
        if not norm or norm in GENERICOS:
            return
        try:
            medio = w.nodes[len(w.nodes) // 2].location
            if not (medio.valid() and dentro(medio.lon, medio.lat)):
                return
            self.tramos[norm].append(self.fabrica.create_linestring(w))
        except Exception:  # noqa: BLE001 - tramos con nodos sin ubicación: se ignoran
            return
        self.nombres.setdefault(norm, t["name"])

    def node(self, n):
        t = n.tags
        if "addr:housenumber" not in t or "addr:street" not in t or not n.location.valid():
            return
        if not dentro(n.location.lon, n.location.lat):
            return
        m = re.match(r"\s*(\d{1,5})", t["addr:housenumber"])
        norm = normalizar(t["addr:street"])
        if m and norm:
            self.puertas.append((norm, int(m.group(1)), n.location.lon, n.location.lat))


def dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url.replace("+psycopg", "")
    env = dict(l.split("=", 1) for l in (RAIZ / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))
    return f"postgresql://{env.get('POSTGRES_USER', 'cadete')}:{env['POSTGRES_PASSWORD']}@localhost:5433/{env.get('POSTGRES_DB', 'cadete')}"


def main() -> None:
    archivo = sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / "routing" / "data" / "uruguay.osm.pbf")
    print("Leyendo", archivo, "…")
    lector = Lector()
    lector.apply_file(archivo, locations=True)
    print(f"  {len(lector.tramos)} calles con nombre, {len(lector.puertas)} números de puerta")
    with psycopg.connect(dsn()) as con, con.cursor() as cur:
        cur.execute("TRUNCATE geo_calles, geo_direcciones RESTART IDENTITY")
        with cur.copy("COPY geo_calles (nombre, norm, geom) FROM STDIN") as copia:
            for norm, tramos in lector.tramos.items():
                partes = ",".join(t[len("LINESTRING"):] for t in tramos)
                copia.write_row((lector.nombres[norm], norm, f"SRID=4326;MULTILINESTRING({partes})"))
        with cur.copy("COPY geo_direcciones (calle_norm, numero, geom) FROM STDIN") as copia:
            for norm, numero, lon, lat in lector.puertas:
                copia.write_row((norm, numero, f"SRID=4326;POINT({lon} {lat})"))
        cur.execute("ANALYZE geo_calles")
        cur.execute("ANALYZE geo_direcciones")
        cur.execute("SELECT (SELECT count(*) FROM geo_calles), (SELECT count(*) FROM geo_direcciones)")
        print("Cargado en la base:", cur.fetchone())


if __name__ == "__main__":
    main()
