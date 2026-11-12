from collections.abc import AsyncIterator
from functools import lru_cache

import redis
import redis.asyncio as redis_async

from app.core.config import settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis_async() -> AsyncIterator[redis_async.Redis]:
    """Cliente asíncrono (para los streams en vivo): uno por conexión, se cierra al terminar."""
    cliente = redis_async.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield cliente
    finally:
        await cliente.aclose()
