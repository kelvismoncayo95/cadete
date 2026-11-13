"""Buscar una dirección escrita por una persona y devolver un punto en el mapa.

Usa NUESTROS datos de OpenStreetMap (geo_calles y geo_direcciones, cargados con geocoder/cargar.py): no depende
de ningún servicio externo. Tres casos:
  · «Av. 18 de Julio 1500»  → el punto exacto de esa puerta, o interpolado entre las puertas vecinas;
  · «Colonia y Ejido»       → el cruce de las dos calles;
  · «Colonia»               → un punto en medio de la calle (aproximado).
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.zone import dentro_de_montevideo
from app.services.direcciones import normalizar, parsear

UMBRAL = "0.55"   # qué tan parecido tiene que ser el nombre buscado (0 a 1); tolera palabras de menos y erratas


def _calles(db: Session, consulta: str, cuantas: int) -> list[tuple[str, str]]:
    """Las calles cuyo nombre contiene lo escrito, las más parecidas primero (y, a igual parecido, las más cortas:
    «colonia» antes que «colonia del sacramento»). Devuelve (nombre, norm)."""
    db.execute(text("SELECT set_config('pg_trgm.word_similarity_threshold', :u, true)"), {"u": UMBRAL})
    filas = db.execute(text(
        "SELECT nombre, norm FROM geo_calles WHERE :q <% norm "
        "ORDER BY word_similarity(:q, norm) DESC, length(norm), norm LIMIT :n"), {"q": consulta, "n": cuantas})
    return [(f[0], f[1]) for f in filas]


def _punto_con_numero(db: Session, norm: str, numero: int) -> tuple[float, float, bool] | None:
    """(lat, lon, exacta) de esa puerta: exacta si existe en OSM; si no, interpolada entre las puertas vecinas."""
    def uno(donde: str, orden: str):
        return db.execute(text(
            f"SELECT numero, ST_Y(geom), ST_X(geom) FROM geo_direcciones WHERE calle_norm = :c AND numero {donde} :n "
            f"ORDER BY (numero % 2 = :n % 2) DESC, {orden} LIMIT 1"), {"c": norm, "n": numero}).first()

    exacto = db.execute(text("SELECT ST_Y(geom), ST_X(geom) FROM geo_direcciones WHERE calle_norm = :c AND numero = :n LIMIT 1"),
                        {"c": norm, "n": numero}).first()
    if exacto:
        return exacto[0], exacto[1], True
    menor, mayor = uno("<", "numero DESC"), uno(">", "numero ASC")   # prefiere el mismo lado de la calle (misma paridad)
    if menor and mayor:
        t = (numero - menor[0]) / (mayor[0] - menor[0])
        return menor[1] + (mayor[1] - menor[1]) * t, menor[2] + (mayor[2] - menor[2]) * t, False
    vecino = menor or mayor
    return (vecino[1], vecino[2], False) if vecino else None


def _medio_de_la_calle(db: Session, norm: str) -> tuple[float, float] | None:
    fila = db.execute(text(
        "SELECT ST_Y(pt), ST_X(pt) FROM (SELECT ST_LineInterpolatePoint(d.geom, 0.5) AS pt "
        "FROM geo_calles c, LATERAL ST_Dump(ST_LineMerge(c.geom)) d WHERE c.norm = :c "
        "ORDER BY ST_Length(d.geom) DESC LIMIT 1) x"), {"c": norm}).first()
    return (fila[0], fila[1]) if fila else None


def _cruce(db: Session, norm_a: str, norm_b: str) -> tuple[float, float, bool] | None:
    """El cruce de dos calles (exacto) o, si en OpenStreetMap no se tocan pero están a menos de 200 m,
    el punto más cercano entre ellas (aproximado)."""
    fila = db.execute(text(
        "SELECT ST_Y(p.geom), ST_X(p.geom) FROM geo_calles a, geo_calles b, LATERAL ST_Dump(ST_Intersection(a.geom, b.geom)) p "
        "WHERE a.norm = :a AND b.norm = :b AND a.id <> b.id AND GeometryType(p.geom) = 'POINT' LIMIT 1"),
        {"a": norm_a, "b": norm_b}).first()
    if fila:
        return fila[0], fila[1], True
    cerca = db.execute(text(
        "SELECT ST_Y(pt), ST_X(pt) FROM (SELECT ST_ClosestPoint(a.geom, b.geom) AS pt, "
        "ST_Distance(a.geom::geography, b.geom::geography) AS d FROM geo_calles a, geo_calles b "
        "WHERE a.norm = :a AND b.norm = :b AND a.id <> b.id ORDER BY d LIMIT 1) x WHERE d <= 200"),
        {"a": norm_a, "b": norm_b}).first()
    return (cerca[0], cerca[1], False) if cerca else None


def _en_la_zona(resultados: list[dict]) -> list[dict]:
    """Los datos cargados cubren un poco más que la zona de entrega: se descarta lo que cae afuera
    (por ejemplo, una calle del mismo nombre en Canelones)."""
    return [r for r in resultados if dentro_de_montevideo(r["lat"], r["lon"])]


def _resultado(etiqueta: str, lat: float, lon: float, exacta: bool) -> dict:
    return {"etiqueta": etiqueta, "lat": lat, "lon": lon, "exacta": exacta}


def buscar(db: Session, escrito: str, limite: int = 5) -> list[dict]:
    calle, numero, calle2 = parsear(escrito)
    resultados: list[dict] = []

    if calle2:   # «A y B»: el cruce
        for nombre_a, norm_a in _calles(db, calle, 4):
            for nombre_b, norm_b in _calles(db, calle2, 4):
                punto = _cruce(db, norm_a, norm_b) if norm_a != norm_b else None
                if punto:
                    resultados.append(_resultado(f"{nombre_a} y {nombre_b}", *punto))
        resultados = _en_la_zona(resultados)
        resultados.sort(key=lambda r: not r["exacta"])   # primero los cruces exactos
        if resultados:
            return resultados[:limite]
        calle, numero = normalizar(escrito), None   # quizá era UNA calle con «y» en el nombre (José Batlle y Ordóñez)

    if numero is not None:   # «calle número»
        for nombre, norm in _calles(db, calle, 8):
            punto = _punto_con_numero(db, norm, numero)
            if punto is None:   # esa calle no tiene puertas cargadas: se ubica en medio de la calle
                medio = _medio_de_la_calle(db, norm)
                punto = (*medio, False) if medio else None
            if punto:
                resultados.append(_resultado(f"{nombre} {numero}", *punto))
        resultados = _en_la_zona(resultados)
        resultados.sort(key=lambda r: not r["exacta"])   # primero las puertas exactas (orden estable)
        if resultados:
            return resultados[:limite]
        calle = normalizar(escrito)   # «Ruta 8»: el número era parte del nombre

    for nombre, norm in _calles(db, calle, limite + 6):   # solo la calle
        medio = _medio_de_la_calle(db, norm)
        if medio:
            resultados.append(_resultado(nombre, *medio, False))
    return _en_la_zona(resultados)[:limite]
