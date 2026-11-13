"""Rutas por calles.

El motor real es OSRM (open source, corre en nuestra máquina con los datos de OpenStreetMap). Respeta los
sentidos únicos y los giros prohibidos: una ruta nunca va en contramano. Si OSRM no responde, el sistema
sigue funcionando con un respaldo en línea recta (peor, pero no se cae) y lo avisa.

Los puntos son siempre (lat, lon) hacia afuera; OSRM usa (lon, lat) y la conversión se hace acá, en un solo lugar.
"""
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.services.geo import distancia_m

log = logging.getLogger("cadete.rutas")
Punto = tuple[float, float]   # (lat, lon)


@dataclass(frozen=True)
class Ruta:
    distancia_m: float
    duracion_s: float
    coordenadas: list[Punto]   # la polilínea, esquina por esquina


class Router(Protocol):
    def ruta(self, puntos: list[Punto]) -> Ruta | None: ...
    def tabla(self, origenes: list[Punto], destino: Punto) -> list[tuple[float, float] | None] | None: ...
    def ajustar(self, punto: Punto) -> tuple[Punto, float] | None: ...


class RectaRouter:
    """Respaldo: línea recta a velocidad fija."""

    usando_respaldo = True

    def __init__(self, velocidad_kmh: float | None = None):
        self.velocidad_ms = (velocidad_kmh or settings.velocidad_estimada_kmh) / 3.6

    def ruta(self, puntos: list[Punto]) -> Ruta:
        metros = sum(distancia_m(*a, *b) for a, b in zip(puntos, puntos[1:]))
        return Ruta(metros, metros / self.velocidad_ms, list(puntos))

    def tabla(self, origenes: list[Punto], destino: Punto) -> list[tuple[float, float] | None]:
        return [(d / self.velocidad_ms, d) for d in (distancia_m(*o, *destino) for o in origenes)]

    def ajustar(self, punto: Punto) -> tuple[Punto, float]:
        return punto, 0.0


def _lonlat(puntos: list[Punto]) -> str:
    return ";".join(f"{lon},{lat}" for lat, lon in puntos)


class OsrmRouter:
    def __init__(self, url: str, cliente: httpx.Client | None = None):
        self.cliente = cliente or httpx.Client(base_url=url, timeout=settings.osrm_timeout_s)

    def _get(self, ruta: str, consulta: str) -> dict | None:
        try:
            r = self.cliente.get(f"{ruta}?{consulta}")   # consulta ya armada: httpx cambiaría los «;» por %3B
            r.raise_for_status()
            datos = r.json()
        except (httpx.HTTPError, ValueError):
            return None
        return datos if datos.get("code") == "Ok" else None

    def ruta(self, puntos: list[Punto]) -> Ruta | None:
        datos = self._get(f"/route/v1/driving/{_lonlat(puntos)}", "overview=full&geometries=geojson&steps=false")
        if not datos or not datos.get("routes"):
            return None
        r = datos["routes"][0]
        return Ruta(r["distance"], r["duration"], [(lat, lon) for lon, lat in r["geometry"]["coordinates"]])

    def tabla(self, origenes: list[Punto], destino: Punto) -> list[tuple[float, float] | None] | None:
        n = len(origenes)
        datos = self._get(
            f"/table/v1/driving/{_lonlat([*origenes, destino])}",
            f"sources={';'.join(str(i) for i in range(n))}&destinations={n}&annotations=duration,distance",
        )
        if not datos:
            return None
        return [
            None if d[0] is None or m[0] is None else (d[0], m[0])
            for d, m in zip(datos["durations"], datos["distances"])
        ]

    def ajustar(self, punto: Punto) -> tuple[Punto, float] | None:
        datos = self._get(f"/nearest/v1/driving/{_lonlat([punto])}", "number=1")
        if not datos or not datos.get("waypoints"):
            return None
        w = datos["waypoints"][0]
        return (w["location"][1], w["location"][0]), w["distance"]


class ConRespaldo:
    """Usa OSRM y, si no responde, la línea recta. `usando_respaldo` dice cuál fue lo último que se usó."""

    def __init__(self, principal: OsrmRouter, respaldo: RectaRouter):
        self.principal, self.respaldo, self.usando_respaldo = principal, respaldo, False

    def _con_respaldo(self, nombre: str, *args):
        resultado = getattr(self.principal, nombre)(*args)
        if resultado is None:
            if not self.usando_respaldo:
                log.warning("OSRM no responde: se usa línea recta como respaldo")
            self.usando_respaldo = True
            return getattr(self.respaldo, nombre)(*args)
        self.usando_respaldo = False
        return resultado

    def ruta(self, puntos):
        return self._con_respaldo("ruta", puntos)

    def tabla(self, origenes, destino):
        return self._con_respaldo("tabla", origenes, destino)

    def ajustar(self, punto):
        return self._con_respaldo("ajustar", punto)


_router: Router | None = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = ConRespaldo(OsrmRouter(settings.osrm_url), RectaRouter())
    return _router


def usar_router(router: Router | None) -> None:
    """Cambia el router (los tests usan uno falso). `None` vuelve al real."""
    global _router
    _router = router
