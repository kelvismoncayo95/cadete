from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import usuario_actual
from app.core.database import get_db
from app.models import User
from app.services.pagos import saldo

router = APIRouter(tags=["pagos"])


@router.get("/wallet")
def mi_billetera(usuario: User = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Mi saldo, lo de hoy y mis últimos movimientos (dinero de juguete). Cada uno ve solo lo suyo."""
    return saldo(db, usuario.id)
