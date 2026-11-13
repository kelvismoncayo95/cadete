import redis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import String, cast, func, select, text
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.core.observability import metricas
from app.core.redis import get_redis
from app.models import AuditLog, Courier, DispatchOffer, Order, User
from app.models.order import ESTADOS
from app.services.routing import get_router
from app.services.heartbeat import LIMITE_SANO_S, edad_s

router = APIRouter(tags=["operación"])
ESTADOS_REPARTIDOR = ("offline", "available", "busy")
ESTADOS_OFERTA = ("pendiente", "aceptada", "rechazada", "expirada")


def _por_estado(db: Session, columna, nombres) -> dict[str, int]:
    cuentas = dict(db.execute(select(columna, func.count()).group_by(columna)).all())
    return {n: cuentas.get(n, 0) for n in nombres}   # los estados sin filas también aparecen (en 0)


@router.get("/metrics")
def metricas_prometheus(db: Session = Depends(get_db), r: redis.Redis = Depends(get_redis)) -> Response:
    """Métricas en el formato de texto de Prometheus. Solo números agregados (sin datos de personas)."""
    lineas = metricas.lineas()
    for nombre, columna, estados, ayuda in (
        ("cadete_orders", Order.status, ESTADOS, "Pedidos por estado"),
        ("cadete_couriers", Courier.status, ESTADOS_REPARTIDOR, "Repartidores por estado"),
        ("cadete_offers", DispatchOffer.status, ESTADOS_OFERTA, "Ofertas de despacho por estado"),
    ):
        lineas += [f"# HELP {nombre} {ayuda}", f"# TYPE {nombre} gauge"]
        lineas += [f'{nombre}{{status="{e}"}} {n}' for e, n in _por_estado(db, columna, estados).items()]
    lineas += ["# HELP cadete_heartbeat_age_seconds Segundos desde el último latido de cada proceso (-1 = sin latido)",
               "# TYPE cadete_heartbeat_age_seconds gauge"]
    for proceso in ("worker", "simulador"):
        edad = edad_s(r, proceso)
        lineas.append(f'cadete_heartbeat_age_seconds{{process="{proceso}"}} {-1 if edad is None else round(edad, 1)}')
    return Response("\n".join(lineas) + "\n", media_type="text/plain; version=0.0.4")


@router.get("/admin/system")
def estado_del_sistema(
    _: User = Depends(requiere_rol("admin")), db: Session = Depends(get_db), r: redis.Redis = Depends(get_redis)
):
    """Salud del sistema para el panel del administrador: base, Redis y los procesos en segundo plano."""
    checks: dict[str, dict] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["db"] = {"ok": True}
    except Exception as e:  # noqa: BLE001
        checks["db"] = {"ok": False, "error": str(e)[:120]}
    try:
        r.ping()
        checks["redis"] = {"ok": True}
    except Exception as e:  # noqa: BLE001
        checks["redis"] = {"ok": False, "error": str(e)[:120]}
    for proceso in ("worker", "simulador"):
        edad = edad_s(r, proceso) if checks["redis"]["ok"] else None
        checks[proceso] = {"ok": edad is not None and edad <= LIMITE_SANO_S, "edad_s": None if edad is None else round(edad, 1)}
    router = get_router()
    router.ajustar((-34.9065, -56.1995))   # una consulta de prueba: así sabemos si el motor de rutas responde
    checks["rutas"] = {"ok": not router.usando_respaldo, "motor": "recta" if router.usando_respaldo else "osrm"}
    if not (checks["db"]["ok"] and checks["redis"]["ok"]):
        estado = "caido"
    elif not checks["worker"]["ok"] or not checks["rutas"]["ok"]:
        estado = "degradado"   # sin trabajador no vencen las ofertas; sin motor de rutas se usa línea recta
    else:
        estado = "ok"          # el simulador es opcional: no cuenta
    sin_repartidor = 0
    if checks["db"]["ok"]:
        # Avisos de «sin repartidor» de pedidos que siguen listos (los ya asignados dejan de contar).
        sin_repartidor = db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "sin_repartidor",
                AuditLog.entity_id.in_(select(cast(Order.id, String)).where(Order.status == "listo")),
            )
        ) or 0
    return {"status": estado, "checks": checks, "alertas": {"pedidos_sin_repartidor": sin_repartidor}}
