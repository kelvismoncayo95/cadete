import redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import usuario_actual
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import User
from app.services.errors import ErrorDeNegocio
from app.services.geocodificador import buscar
from app.services.rate_limit import bloqueado, registrar_fallo

router = APIRouter(tags=["direcciones"])
MAX_BUSQUEDAS_POR_MINUTO = 30


@router.get("/geocode")
def buscar_direccion(
    q: str = Query(min_length=3, max_length=120, description="Una dirección: «Av. 18 de Julio 1500» o «Colonia y Ejido»"),
    usuario: User = Depends(usuario_actual),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """Busca la dirección en nuestros datos de OpenStreetMap y devuelve hasta 5 puntos posibles."""
    clave = f"geocode:{usuario.id}"
    if bloqueado(r, clave, MAX_BUSQUEDAS_POR_MINUTO):
        raise ErrorDeNegocio(429, "Demasiadas búsquedas seguidas. Esperá un momento.")
    registrar_fallo(r, clave, 60)   # cuenta cada búsqueda
    return {"resultados": buscar(db, q)}
