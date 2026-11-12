import math

RADIO_TIERRA_M = 6_371_000


def distancia_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta entre dos puntos, en metros (fórmula de haversine)."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df, dl = f2 - f1, math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(a))


def mover_hacia(lat: float, lon: float, dest_lat: float, dest_lon: float, metros: float) -> tuple[float, float]:
    """Avanza `metros` en línea recta hacia el destino (sin pasarse si ya está cerca)."""
    total = distancia_m(lat, lon, dest_lat, dest_lon)
    if total <= metros:
        return dest_lat, dest_lon
    fraccion = metros / total
    return lat + (dest_lat - lat) * fraccion, lon + (dest_lon - lon) * fraccion


def minutos_estimados(metros: float, velocidad_kmh: float) -> int:
    """Minutos para recorrer esa distancia, redondeados hacia arriba (0 solo si no hay distancia)."""
    if metros <= 0:
        return 0
    return math.ceil(metros / (velocidad_kmh * 1000 / 60))
