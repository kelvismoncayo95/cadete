import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decodificar_token
from app.models import User

bearer = HTTPBearer(auto_error=False)


def _no_autenticado(mensaje: str) -> HTTPException:
    return HTTPException(401, mensaje, headers={"WWW-Authenticate": "Bearer"})


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credenciales is None:
        raise _no_autenticado("Necesitás iniciar sesión")
    try:
        datos = decodificar_token(credenciales.credentials)
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


def requiere_rol(*roles: str) -> Callable[[User], User]:
    def comprobar(usuario: User = Depends(usuario_actual)) -> User:
        if usuario.role not in roles:
            raise HTTPException(403, "No tenés permiso para hacer esto")
        return usuario

    return comprobar
