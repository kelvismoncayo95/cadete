import uuid

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import usuario_actual
from app.core.database import get_db
from app.models import Merchant, Product, User
from app.schemas.catalog import MerchantOut, ProductOut

router = APIRouter(tags=["catálogo"])


@router.get("/merchants", response_model=list[MerchantOut])
def comercios_abiertos(_: User = Depends(usuario_actual), db: Session = Depends(get_db)):
    geometria = cast(Merchant.location, Geometry)
    filas = db.execute(
        select(Merchant, func.ST_Y(geometria).label("lat"), func.ST_X(geometria).label("lon"))
        .where(Merchant.is_open.is_(True))
        .order_by(Merchant.name)
    )
    return [
        MerchantOut(id=m.id, name=m.name, category=m.category, address=m.address, lat=lat, lon=lon)
        for m, lat, lon in filas
    ]


@router.get("/merchants/{merchant_id}/products", response_model=list[ProductOut])
def productos_de_un_comercio(
    merchant_id: uuid.UUID, _: User = Depends(usuario_actual), db: Session = Depends(get_db)
):
    if db.get(Merchant, merchant_id) is None:
        raise HTTPException(404, "No encontramos ese comercio")
    return db.scalars(
        select(Product)
        .where(Product.merchant_id == merchant_id, Product.is_available.is_(True))
        .order_by(Product.name)
    ).all()
