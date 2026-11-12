import redis


def bloqueado(r: redis.Redis, clave: str, maximo: int) -> bool:
    return int(r.get(clave) or 0) >= maximo


def registrar_fallo(r: redis.Redis, clave: str, ventana_segundos: int) -> None:
    if r.incr(clave) == 1:
        r.expire(clave, ventana_segundos)
