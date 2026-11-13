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


def punto_a_distancia(coordenadas: list[tuple[float, float]], metros: float) -> tuple[float, float, bool]:
    """Camina `metros` por una polilínea de calles [(lat, lon), ...] (doblando en cada esquina).

    Devuelve (lat, lon, llegó_al_final)."""
    if len(coordenadas) < 2:
        return (*coordenadas[0], True)
    restante = metros
    for (lat1, lon1), (lat2, lon2) in zip(coordenadas, coordenadas[1:]):
        tramo = distancia_m(lat1, lon1, lat2, lon2)
        if restante <= tramo and tramo > 0:
            lat, lon = mover_hacia(lat1, lon1, lat2, lon2, restante)
            return lat, lon, False
        restante -= tramo
    return (*coordenadas[-1], True)
