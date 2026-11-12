import uuid

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import requiere_rol
from app.models import Merchant, Order
from tests.helpers import cabecera, crear_pedido, crear_repartidor


def datos(sesion, pedido_id):
    pedido = sesion.get(Order, pedido_id)
    dueno = sesion.get(Merchant, pedido.merchant_id).user_id
    return pedido, pedido.customer_user_id, dueno


def test_el_cliente_ve_solo_sus_pedidos(cliente, sesion):
    mio = crear_pedido(sesion)
    ajeno = crear_pedido(sesion)
    _, mi_usuario, _ = datos(sesion, mio)
    r = cliente.get("/orders", headers=cabecera(mi_usuario))
    assert [p["id"] for p in r.json()] == [str(mio)]
    assert cliente.get(f"/orders/{mio}", headers=cabecera(mi_usuario)).status_code == 200
    # El de otra persona no existe para mí: 404, no 403.
    r = cliente.get(f"/orders/{ajeno}", headers=cabecera(mi_usuario))
    assert r.status_code == 404
    assert r.json()["detail"] == "No encontramos ese pedido"


def test_el_comercio_ve_solo_los_pedidos_de_su_local(cliente, sesion):
    suyo = crear_pedido(sesion)
    otro = crear_pedido(sesion)
    _, _, dueno = datos(sesion, suyo)
    r = cliente.get("/orders", headers=cabecera(dueno))
    assert [p["id"] for p in r.json()] == [str(suyo)]
    assert cliente.get(f"/orders/{otro}", headers=cabecera(dueno)).status_code == 404


def test_el_repartidor_ve_solo_los_pedidos_que_tiene_asignados(cliente, sesion):
    asignado = crear_pedido(sesion, "asignado")
    otro = crear_pedido(sesion, "listo")
    repartidor = crear_repartidor(sesion)
    sesion.get(Order, asignado).courier_id = repartidor.id
    sesion.commit()
    r = cliente.get("/orders", headers=cabecera(repartidor.user_id))
    assert [p["id"] for p in r.json()] == [str(asignado)]
    assert cliente.get(f"/orders/{otro}", headers=cabecera(repartidor.user_id)).status_code == 404


def test_el_admin_ve_todo(cliente, sesion):
    from app.models import User

    crear_pedido(sesion)
    crear_pedido(sesion)
    admin = User(username="adm", password_hash="h", display_name="Admin", role="admin")
    sesion.add(admin)
    sesion.commit()
    assert len(cliente.get("/orders", headers=cabecera(admin.id)).json()) == 2


def test_sin_token_no_se_ve_nada(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    assert cliente.get("/orders").status_code == 401
    assert cliente.get(f"/orders/{pedido_id}").status_code == 401


def test_pedido_con_id_inexistente_da_404(cliente, sesion):
    _, usuario, _ = datos(sesion, crear_pedido(sesion))
    assert cliente.get(f"/orders/{uuid.uuid4()}", headers=cabecera(usuario)).status_code == 404


def test_un_rol_equivocado_da_403(cliente, sesion):
    """Un cliente no puede usar algo reservado al admin."""
    app = FastAPI()
    from app.core.database import get_db

    app.dependency_overrides[get_db] = cliente.app.dependency_overrides[get_db]

    @app.get("/solo-admin", dependencies=[Depends(requiere_rol("admin"))])
    def solo_admin():
        return {"ok": True}

    _, usuario, _ = datos(sesion, crear_pedido(sesion))
    r = TestClient(app).get("/solo-admin", headers=cabecera(usuario))
    assert r.status_code == 403
