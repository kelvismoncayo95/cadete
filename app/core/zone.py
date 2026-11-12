"""Zona de entrega: un rectángulo aproximado del departamento de Montevideo.

Es una aproximación simple. En el paso 11, con el mapa, se puede afinar con el contorno real.
"""
LAT_MIN, LAT_MAX = -34.95, -34.74
LON_MIN, LON_MAX = -56.43, -56.01


def dentro_de_montevideo(lat: float, lon: float) -> bool:
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX
