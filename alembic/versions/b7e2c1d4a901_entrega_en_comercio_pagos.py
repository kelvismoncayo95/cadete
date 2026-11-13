"""entrega en el comercio y pagos

- Estado nuevo «en_comercio» (el repartidor llegó al comercio) entre «asignado» y «en_camino».
- orders.courier_pay_cents: lo que cobra el repartidor por el pedido.
- ledger_entries: libro de movimientos (cobro al cliente, pago al comercio y al repartidor, plataforma).

Revision ID: b7e2c1d4a901
Revises: 8e137d744115
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c1d4a901"
down_revision: Union[str, None] = "8e137d744115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESTADOS_NUEVOS = ("recibido", "aceptado", "preparando", "listo", "asignado", "en_comercio",
                  "en_camino", "entregado", "rechazado", "cancelado")
ESTADOS_VIEJOS = tuple(e for e in ESTADOS_NUEVOS if e != "en_comercio")


def _lista(estados):
    return ",".join(f"'{e}'" for e in estados)


def upgrade() -> None:
    op.add_column("orders", sa.Column("courier_pay_cents", sa.BigInteger(), nullable=True))
    op.drop_constraint(op.f("ck_orders_status"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_status"), "orders", f"status IN ({_lista(ESTADOS_NUEVOS)})")
    # Un repartidor sigue sin poder tener dos pedidos activos: ahora «activo» incluye en_comercio.
    op.drop_index("ux_courier_active_order", table_name="orders")
    op.create_index("ux_courier_active_order", "orders", ["courier_id"], unique=True,
                    postgresql_where=sa.text("status IN ('asignado','en_comercio','en_camino')"))
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("concept", sa.String(length=30), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_ledger_entries_order_id_orders")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_ledger_entries_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
        sa.UniqueConstraint("order_id", "concept", name="uq_ledger_entries_order_concept"),
    )
    op.create_index("ix_ledger_entries_user_id", "ledger_entries", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_user_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.execute("UPDATE orders SET status = 'asignado' WHERE status = 'en_comercio'")
    op.drop_index("ux_courier_active_order", table_name="orders")
    op.create_index("ux_courier_active_order", "orders", ["courier_id"], unique=True,
                    postgresql_where=sa.text("status IN ('asignado','en_camino')"))
    op.drop_constraint(op.f("ck_orders_status"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_status"), "orders", f"status IN ({_lista(ESTADOS_VIEJOS)})")
    op.drop_column("orders", "courier_pay_cents")
