from app.core.security import crear_token
from app.models import User
from app.seed import DEMO_PASSWORD, seed_usuarios


def login(cliente, usuario, clave):
    return cliente.post("/auth/login", json={"username": usuario, "password": clave})


def test_login_correcto_devuelve_token_y_rol(cliente, sesion):
    seed_usuarios(sesion)
    r = login(cliente, "ana", DEMO_PASSWORD)
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["role"] == "customer"
    assert r.json()["access_token"]


def test_contrasena_incorrecta_da_401(cliente, sesion):
    seed_usuarios(sesion)
    r = login(cliente, "ana", "mala")
    assert r.status_code == 401
    assert r.json()["detail"] == "Usuario o contraseña incorrectos"


def test_usuario_inexistente_da_el_mismo_401(cliente, sesion):
    seed_usuarios(sesion)
    r = login(cliente, "fantasma", "demo1234")
    assert r.status_code == 401
    assert r.json()["detail"] == "Usuario o contraseña incorrectos"


def test_usuario_inactivo_no_entra(cliente, sesion):
    seed_usuarios(sesion)
    sesion.query(User).filter_by(username="ana").update({"is_active": False})
    sesion.commit()
    assert login(cliente, "ana", DEMO_PASSWORD).status_code == 401


def test_demasiados_intentos_fallidos_dan_429(cliente, sesion):
    seed_usuarios(sesion)
    for _ in range(10):
        assert login(cliente, "ana", "mala").status_code == 401
    r = login(cliente, "ana", DEMO_PASSWORD)
    assert r.status_code == 429
    assert "Demasiados intentos" in r.json()["detail"]


def test_me_devuelve_mis_datos_sin_el_hash(cliente, sesion):
    seed_usuarios(sesion)
    token = login(cliente, "luis", DEMO_PASSWORD).json()["access_token"]
    r = cliente.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "luis"
    assert r.json()["role"] == "courier"
    assert "password_hash" not in r.json()


def test_me_sin_token_da_401(cliente):
    assert cliente.get("/me").status_code == 401


def test_token_vencido_da_401_con_mensaje(cliente, sesion):
    seed_usuarios(sesion)
    ana = sesion.query(User).filter_by(username="ana").one()
    token = crear_token(ana.id, minutos=-1)
    r = cliente.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Tu sesión venció"


def test_token_basura_da_401(cliente):
    r = cliente.get("/me", headers={"Authorization": "Bearer esto-no-es-un-token"})
    assert r.status_code == 401
