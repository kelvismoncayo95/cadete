import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def hashear(clave: str) -> str:
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verificar(clave: str, hash_guardado: str) -> bool:
    return bcrypt.checkpw(clave.encode(), hash_guardado.encode())


def crear_token(usuario_id: uuid.UUID, minutos: int | None = None) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("Falta JWT_SECRET en el entorno o en el .env")
    ahora = datetime.now(timezone.utc)
    duracion = settings.jwt_expire_minutes if minutos is None else minutos
    datos = {"sub": str(usuario_id), "iat": ahora, "exp": ahora + timedelta(minutes=duracion)}
    return jwt.encode(datos, settings.jwt_secret, algorithm="HS256")


def decodificar_token(token: str) -> dict[str, Any]:
    """Devuelve los datos del token. Lanza ExpiredSignatureError o InvalidTokenError."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
