"""Proceso del simulador. Uso:  python -m app.simulator.main"""
import logging
import time

from app.core.database import SessionLocal
from app.core.observability import configurar_logs
from app.services.heartbeat import latir
from app.core.redis import get_redis
from app.simulator.engine import Config, tick

log = logging.getLogger("cadete.simulador")


def main() -> None:
    configurar_logs()
    cfg = Config()
    r = get_redis()
    log.info("simulador iniciado")
    while True:
        try:
            with SessionLocal() as db:
                resumen = tick(db, r, cfg=cfg)
            latir(r, "simulador")
            if any(resumen.values()):
                log.info("%s", resumen)
        except Exception:  # noqa: BLE001 - el simulador no debe caerse por un error puntual
            log.exception("error en la vuelta")
        time.sleep(cfg.tick_s)


if __name__ == "__main__":
    main()
