"""Latido: cada proceso en segundo plano avisa en Redis que sigue vivo. Si el latido se apaga, algo anda mal."""
from datetime import datetime, timezone

import redis

VIGENCIA_S = 120
LIMITE_SANO_S = 60   # más viejo que esto = el proceso se colgó o se cayó


def latir(r: redis.Redis, nombre: str) -> None:
    r.set(f"heartbeat:{nombre}", datetime.now(timezone.utc).isoformat(), ex=VIGENCIA_S)


def edad_s(r: redis.Redis, nombre: str) -> float | None:
    """Segundos desde el último latido, o None si nunca latió (o venció)."""
    valor = r.get(f"heartbeat:{nombre}")
    if not valor:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(valor)).total_seconds()
