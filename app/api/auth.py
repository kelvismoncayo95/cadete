import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_actual
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import crear_token, hashear, verificar
from app.models import User
from app.schemas.auth import LoginIn, MeOut, TokenOut
from app.services.rate_limit import bloqueado, registrar_fallo

router = APIRouter(tags=["auth"])

# Hash de mentira: así tarda lo mismo si el usuario no existe (no se puede adivinar quién existe).
_HASH_FALSO = hashear("no-existe")


@router.post("/auth/login", response_model=TokenOut)
def login(
    datos: LoginIn,
    request: Request,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> TokenOut:
    ip = request.client.host if request.client else "desconocida"
    clave = f"login_fallos:{ip}"
    if bloqueado(r, clave, settings.login_max_intentos):
        raise HTTPException(429, "Demasiados intentos. Esperá un momento")

    usuario = db.scalar(select(User).where(User.username == datos.username))
    hash_guardado = usuario.password_hash if usuario else _HASH_FALSO
    clave_ok = verificar(datos.password, hash_guardado)
    if usuario is None or not clave_ok or not usuario.is_active:
        registrar_fallo(r, clave, settings.login_ventana_segundos)
        raise HTTPException(401, "Usuario o contraseña incorrectos")

    return TokenOut(access_token=crear_token(usuario.id), role=usuario.role)


@router.get("/me", response_model=MeOut)
def me(usuario: User = Depends(usuario_actual)) -> User:
    return usuario
