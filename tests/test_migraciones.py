import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.helpers import alembic_cfg

TABLAS = {
    "users", "merchants", "products", "couriers", "orders", "order_items",
    "order_events", "dispatch_offers", "courier_positions", "idempotency_keys",
    "audit_log",
}


def test_upgrade_crea_todas_las_tablas(base_vacia):
    command.upgrade(alembic_cfg(), "head")
    assert TABLAS <= set(inspect(base_vacia).get_table_names())


def test_downgrade_deja_la_base_sin_tablas(base_vacia):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "base")
    assert not (TABLAS & set(inspect(base_vacia).get_table_names()))


def test_los_ids_expuestos_son_uuid(migrada):
    insp = inspect(migrada)
    for tabla in ("users", "merchants", "products", "couriers", "orders", "dispatch_offers"):
        columnas = {c["name"]: str(c["type"]) for c in insp.get_columns(tabla)}
        assert columnas["id"] == "UUID", tabla


def test_rol_invalido_es_rechazado(migrada):
    with pytest.raises(IntegrityError):
        with migrada.begin() as con:
            con.execute(text(
                "INSERT INTO users (username, password_hash, display_name, role) "
                "VALUES ('x', 'h', 'X', 'superheroe')"
            ))


def _crear_pedido_activo(con, courier_id, customer_id, merchant_id, estado):
    con.execute(text(
        "INSERT INTO orders (customer_user_id, merchant_id, courier_id, status, "
        "delivery_address, delivery_location, subtotal_cents, delivery_fee_cents, total_cents) "
        "VALUES (:c, :m, :k, :s, 'calle', 'SRID=4326;POINT(-56.16 -34.9)', 100, 6000, 6100)"
    ), {"c": customer_id, "m": merchant_id, "k": courier_id, "s": estado})


def test_un_repartidor_no_puede_tener_dos_pedidos_activos(migrada):
    with migrada.begin() as con:
        ids = {}
        for nombre, rol in (("cli", "customer"), ("com", "merchant"), ("rep", "courier")):
            ids[rol] = con.execute(text(
                "INSERT INTO users (username, password_hash, display_name, role) "
                "VALUES (:u, 'h', :u, :r) RETURNING id"
            ), {"u": nombre, "r": rol}).scalar_one()
        merchant = con.execute(text(
            "INSERT INTO merchants (user_id, name, category, address, location) "
            "VALUES (:u, 'Demo', 'comida', 'calle', 'SRID=4326;POINT(-56.15 -34.9)') RETURNING id"
        ), {"u": ids["merchant"]}).scalar_one()
        courier = con.execute(text(
            "INSERT INTO couriers (user_id, vehicle) VALUES (:u, 'moto') RETURNING id"
        ), {"u": ids["courier"]}).scalar_one()
        _crear_pedido_activo(con, courier, ids["customer"], merchant, "asignado")
    with pytest.raises(IntegrityError):
        with migrada.begin() as con:
            _crear_pedido_activo(con, courier, ids["customer"], merchant, "en_camino")


def test_comercio_sin_ubicacion_es_rechazado(migrada):
    with pytest.raises(IntegrityError):
        with migrada.begin() as con:
            uid = con.execute(text(
                "INSERT INTO users (username, password_hash, display_name, role) "
                "VALUES ('com2', 'h', 'Com', 'merchant') RETURNING id"
            )).scalar_one()
            con.execute(text(
                "INSERT INTO merchants (user_id, name, category, address) "
                "VALUES (:u, 'Demo', 'comida', 'calle')"
            ), {"u": uid})
