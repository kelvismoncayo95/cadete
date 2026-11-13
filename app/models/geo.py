from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GeoCalle(Base):
    """Una calle con nombre (todos sus tramos juntos), de OpenStreetMap. Se carga con geocoder/cargar.py."""

    __tablename__ = "geo_calles"
    __table_args__ = (
        Index("ix_geo_calles_geom", "geom", postgresql_using="gist"),
        Index("ix_geo_calles_norm_trgm", "norm", postgresql_using="gin", postgresql_ops={"norm": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(160))
    norm: Mapped[str] = mapped_column(String(160))
    geom = mapped_column(Geometry("MULTILINESTRING", srid=4326, spatial_index=False), nullable=False)


class GeoDireccion(Base):
    """Un número de puerta (punto) de OpenStreetMap."""

    __tablename__ = "geo_direcciones"
    __table_args__ = (Index("ix_geo_direcciones_calle_numero", "calle_norm", "numero"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    calle_norm: Mapped[str] = mapped_column(String(160))
    numero: Mapped[int] = mapped_column(Integer)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
