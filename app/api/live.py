import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as redis_async
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol, usuario_del_stream
from app.core.database import get_db
from app.core.redis import get_redis_async
from app.models import Order, User
from app.services.events import CANAL_TODO, TERMINALES, canal_pedido, datos_admin, datos_de_pedido
from app.services.permissions import pedidos_visibles

router = APIRouter(tags=["en vivo"])

PING_CADA_SEGUNDOS = 15


def _sse(evento: str, datos: dict[str, Any]) -> str:
    return f"event: {evento}\ndata: {json.dumps(datos)}\n\n"


async def _flujo(
    request: Request, pubsub: redis_async.client.PubSub, inicial: dict[str, Any], cierra_en_terminal: bool
) -> AsyncIterator[str]:
    """Manda la foto inicial y después cada evento que llegue. Un comentario ':ping' cada 15 s
    evita que los intermediarios corten una conexión quieta."""
    try:
        yield _sse(inicial["tipo"], inicial)
        if cierra_en_terminal and inicial.get("status") in TERMINALES:
            return
        ultimo_envio = time.monotonic()
        while True:
            mensaje = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if mensaje:
                datos = json.loads(mensaje["data"])
                yield _sse(datos["tipo"], datos)
                ultimo_envio = time.monotonic()
                if cierra_en_terminal and datos["tipo"] == "estado" and datos.get("status") in TERMINALES:
                    return
            elif time.monotonic() - ultimo_envio > PING_CADA_SEGUNDOS:
                yield ": ping\n\n"
                ultimo_envio = time.monotonic()
            if await request.is_disconnected():
                return
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


def _respuesta(flujo: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        flujo,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/orders/{order_id}/live")
async def seguir_pedido(
    order_id: uuid.UUID,
    request: Request,
    usuario: User = Depends(usuario_del_stream),
    db: Session = Depends(get_db),
    r: redis_async.Redis = Depends(get_redis_async),
):
    def foto_inicial() -> dict[str, Any] | None:
        pedido = db.scalar(pedidos_visibles(usuario).where(Order.id == order_id))
        return datos_de_pedido(db, pedido) if pedido else None

    # Primero me suscribo y después saco la foto: así no se pierde ningún evento entre las dos cosas.
    pubsub = r.pubsub()
    await pubsub.subscribe(canal_pedido(order_id))
    inicial = await run_in_threadpool(foto_inicial)
    if inicial is None:
        await pubsub.aclose()
        raise HTTPException(404, "No encontramos ese pedido")
    return _respuesta(_flujo(request, pubsub, inicial, cierra_en_terminal=True))


@router.get("/admin/live")
async def mapa_del_admin(
    request: Request,
    usuario: User = Depends(requiere_rol("admin", stream=True)),
    db: Session = Depends(get_db),
    r: redis_async.Redis = Depends(get_redis_async),
):
    pubsub = r.pubsub()
    await pubsub.subscribe(CANAL_TODO)
    inicial = await run_in_threadpool(datos_admin, db)
    return _respuesta(_flujo(request, pubsub, inicial, cierra_en_terminal=False))
