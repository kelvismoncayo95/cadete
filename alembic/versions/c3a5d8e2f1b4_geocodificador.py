"""geocodificador propio: calles y números de puerta de OpenStreetMap

Revision ID: c3a5d8e2f1b4
Revises: b7e2c1d4a901
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "c3a5d8e2f1b4"
down_revision: Union[str, None] = "b7e2c1d4a901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")   # búsqueda por parecido de texto
    op.create_table(
        "geo_calles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("norm", sa.String(length=160), nullable=False),
        sa.Column("geom", geoalchemy2.types.Geometry(geometry_type="MULTILINESTRING", srid=4326, dimension=2,
                                                      spatial_index=False, from_text="ST_GeomFromEWKT", name="geometry"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_calles")),
    )
    op.create_index("ix_geo_calles_geom", "geo_calles", ["geom"], unique=False, postgresql_using="gist")
    op.create_index("ix_geo_calles_norm_trgm", "geo_calles", ["norm"], unique=False, postgresql_using="gin",
                    postgresql_ops={"norm": "gin_trgm_ops"})
    op.create_table(
        "geo_direcciones",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("calle_norm", sa.String(length=160), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("geom", geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, dimension=2,
                                                      spatial_index=False, from_text="ST_GeomFromEWKT", name="geometry"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_direcciones")),
    )
    op.create_index("ix_geo_direcciones_calle_numero", "geo_direcciones", ["calle_norm", "numero"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_geo_direcciones_calle_numero", table_name="geo_direcciones")
    op.drop_table("geo_direcciones")
    op.drop_index("ix_geo_calles_norm_trgm", table_name="geo_calles", postgresql_using="gin")
    op.drop_index("ix_geo_calles_geom", table_name="geo_calles", postgresql_using="gist")
    op.drop_table("geo_calles")
    # la extensión pg_trgm se deja instalada (otras cosas podrían usarla)
