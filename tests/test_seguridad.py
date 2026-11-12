import uuid

import pytest
from jwt import ExpiredSignatureError

from app.core.security import crear_token, decodificar_token, hashear, verificar


def test_hash_y_verificacion():
    h = hashear("demo1234")
    assert h != "demo1234"
    assert verificar("demo1234", h)
    assert not verificar("otra", h)


def test_token_ida_y_vuelta():
    uid = uuid.uuid4()
    assert decodificar_token(crear_token(uid))["sub"] == str(uid)


def test_token_vencido():
    with pytest.raises(ExpiredSignatureError):
        decodificar_token(crear_token(uuid.uuid4(), minutos=-1))
