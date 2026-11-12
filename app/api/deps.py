import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decodificar_token
from app.models import User

bearer = HTTPBearer(auto_error=False)


def _no_autenticado(mensaje: str) -> HTTPException:
    return HTTPException(401, mensaje, headers={"WWW-Authenticate": "Bearer"})


def _usuario_desde_token(token: str | None, db: Session) -> User:
    if not token:
        raise _no_autenticado("Necesitás iniciar sesión")
    try:
        datos = decodificar_token(token)
        usuario_id = uuid.UUID(datos["sub"])
    except jwt.ExpiredSignatureError:
        raise _no_autenticado("Tu sesión venció")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise _no_autenticado("Sesión inválida")
    # El rol sale SIEMPRE de la base, no del token: si cambia, vale el nuevo.
    usuario = db.get(User, usuario_id)
    if usuario is None or not usuario.is_active:
        raise _no_autenticado("Sesión inválida")
    return usuario


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    return _usuario_desde_token(credenciales.credentials if credenciales else None, db)


def usuario_del_stream(
    credenciales: HTTPAuthorizationCredentials | None = Depends(bearer),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Para los streams en vivo. El navegador (EventSource) no puede mandar cabeceras,
    así que además de la cabecera Authorization se acepta ?token=. Solo se usa en estos endpoints."""
    return _usuario_desde_token(credenciales.credentials if credenciales else token, db)


def requiere_rol(*roles: str, stream: bool = False) -> Callable[[User], User]:
    origen = usuario_del_stream if stream else usuario_actual

    def comprobar(usuario: User = Depends(origen)) -> User:
        if usuario.role not in roles:
            raise HTTPException(403, "No tenés permiso para hacer esto")
        return usuario

    return comprobar
