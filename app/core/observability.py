"""Observabilidad: logs en JSON con un id por petición, y métricas para /metrics."""
import contextvars
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
log = logging.getLogger("cadete.http")
SILENCIOSAS = ("/health", "/metrics")   # las consultas de salud no ensucian el log


class JsonFormatter(logging.Formatter):
    """Una línea de log = un objeto JSON (fácil de buscar y filtrar en cualquier herramienta)."""

    def format(self, record: logging.LogRecord) -> str:
        datos = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        datos.update(getattr(record, "datos", {}))
        if record.exc_info:
            datos["exc"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False)


def configurar_logs(nivel: int = logging.INFO) -> None:
    raiz = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in raiz.handlers):
        manejador = logging.StreamHandler()
        manejador.setFormatter(JsonFormatter())
        raiz.addHandler(manejador)
    raiz.setLevel(nivel)


class Metricas:
    """Contadores en memoria (por proceso). Las etiquetas usan la PLANTILLA de la ruta, no la URL real:
    así no se crea una serie nueva por cada id."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reiniciar()

    def reiniciar(self) -> None:
        with self._lock:
            self.peticiones: dict[tuple, int] = defaultdict(int)
            self.segundos_suma: dict[tuple, float] = defaultdict(float)

    def observar(self, metodo: str, ruta: str, estado: int, segundos: float) -> None:
        clave = (metodo, ruta, str(estado))
        with self._lock:
            self.peticiones[clave] += 1
            self.segundos_suma[clave] += segundos

    def lineas(self) -> list[str]:
        with self._lock:
            filas = sorted(self.peticiones.items())
            suma = dict(self.segundos_suma)
        salida = ["# HELP cadete_http_requests_total Pedidos HTTP atendidos", "# TYPE cadete_http_requests_total counter"]
        for (m, r, e), n in filas:
            salida.append(f'cadete_http_requests_total{{method="{m}",route="{r}",status="{e}"}} {n}')
        salida += ["# HELP cadete_http_request_seconds_sum Segundos acumulados atendiendo pedidos",
                   "# TYPE cadete_http_request_seconds_sum counter"]
        for (m, r, e), s in sorted(suma.items()):
            salida.append(f'cadete_http_request_seconds_sum{{method="{m}",route="{r}",status="{e}"}} {s:.4f}')
        return salida


metricas = Metricas()


def _plantilla_de_la_ruta(scope: dict) -> str:
    ruta = scope.get("route")
    if ruta is not None and getattr(ruta, "path", None):
        return ruta.path
    return "estatico" if scope.get("path", "").count("/") <= 3 and "." in scope.get("path", "") else "no_encontrada"


class ObservabilidadMiddleware:
    """Middleware ASGI puro (no BaseHTTPMiddleware: no interfiere con los streams SSE).

    Le pone a cada petición un id (X-Request-ID), mide cuánto tarda y la registra."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        entrante = dict(scope["headers"]).get(b"x-request-id", b"").decode()[:64]
        rid = entrante or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        inicio = time.perf_counter()
        estado = {"codigo": 500}

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                estado["codigo"] = mensaje["status"]
                mensaje["headers"] = [*mensaje.get("headers", []), (b"x-request-id", rid.encode())]
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            log.exception("error sin manejar", extra={"datos": {"ruta": scope["path"]}})
            raise
        finally:
            segundos = time.perf_counter() - inicio
            ruta = _plantilla_de_la_ruta(scope)
            metricas.observar(scope["method"], ruta, estado["codigo"], segundos)
            nivel = logging.DEBUG if scope["path"] in SILENCIOSAS else logging.INFO
            log.log(nivel, "http", extra={"datos": {
                "metodo": scope["method"], "ruta": scope["path"], "plantilla": ruta,
                "estado": estado["codigo"], "ms": round(segundos * 1000, 1)}})
            request_id_var.reset(token)
