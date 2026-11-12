"""Trabajador en segundo plano: mantiene vivo el despacho.

  - cada 5 s:  expira las ofertas vencidas y las pasa al siguiente repartidor
  - cada 30 s: reintenta los pedidos listos sin repartidor y avisa a los 10 minutos
  - cada hora: borra posiciones de más de 7 días

Es un bucle simple que consulta la base (la fuente de verdad). Si se reinicia, no pierde nada:
las ofertas y los pedidos siguen guardados. Más adelante se puede cambiar por una cola (Arq/RQ).

Uso:  python -m app.worker.main
"""
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.observability import configurar_logs
from app.core.redis import get_redis
from app.services.couriers import purgar_posiciones_antiguas
from app.services.heartbeat import latir
from app.services.dispatch import avisar_pedidos_sin_repartidor, expirar_ofertas, reintentar_despachos

log = logging.getLogger("cadete.worker")

CADA_SEGUNDOS = 5
REINTENTO_CADA_VUELTAS = 6      # 6 vueltas de 5 s = 30 s
PURGA_CADA_VUELTAS = 720        # 720 vueltas de 5 s = 1 hora


def ciclo(db: Session, ahora: datetime | None = None, completo: bool = False, r=None) -> dict[str, int]:
    resultado = {"expiradas": expirar_ofertas(db, ahora)}
    if r is not None:
        latir(r, "worker")   # «sigo vivo»: el panel del admin lo mira
    if completo:
        resultado["ofrecidas"] = reintentar_despachos(db, ahora)
        resultado["avisos"] = avisar_pedidos_sin_repartidor(db, ahora)
    return resultado


def main() -> None:
    configurar_logs()
    r = get_redis()
    log.info("trabajador iniciado")
    vuelta = 0
    while True:
        vuelta += 1
        try:
            with SessionLocal() as db:
                resultado = ciclo(db, completo=vuelta % REINTENTO_CADA_VUELTAS == 0, r=r)
                if vuelta % PURGA_CADA_VUELTAS == 0:
                    resultado["posiciones_borradas"] = purgar_posiciones_antiguas(db)
            if any(resultado.values()):
                log.info("vuelta %s: %s", vuelta, resultado)
        except Exception:  # noqa: BLE001 - el trabajador no debe caerse por un error puntual
            log.exception("error en la vuelta %s", vuelta)
        time.sleep(CADA_SEGUNDOS)


if __name__ == "__main__":
    main()
