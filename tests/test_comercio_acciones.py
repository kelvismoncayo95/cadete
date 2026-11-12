from sqlalchemy import select

from app.models import Merchant, Order, OrderEvent, User
from tests.helpers import cabecera, crear_pedido


def dueno_de(sesion, pedido_id) -> User:
    pedido = sesion.get(Order, pedido_id)
    return sesion.get(User, sesion.get(Merchant, pedido.merchant_id).user_id)


def cliente_de(sesion, pedido_id) -> User:
    return sesion.get(User, sesion.get(Order, pedido_id).customer_user_id)


def accion(cliente, usuario, pedido_id, nombre, cuerpo=None):
    return cliente.post(f"/merchant/orders/{pedido_id}/{nombre}", json=cuerpo, headers=cabecera(usuario.id))


def test_el_comercio_lleva_el_pedido_de_recibido_a_listo(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    dueno = dueno_de(sesion, pedido_id)
    for nombre, estado in (("accept", "aceptado"), ("preparing", "preparando"), ("ready", "listo")):
        r = accion(cliente, dueno, pedido_id, nombre)
        assert (r.status_code, r.json()["status"]) == (200, estado)
    sesion.expire_all()
    eventos = sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == pedido_id).order_by(OrderEvent.id)).all()
    assert [e.to_status for e in eventos] == ["aceptado", "preparando", "listo"]
    assert all(e.actor_user_id == dueno.id for e in eventos)


def test_rechazar_guarda_el_motivo(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    dueno = dueno_de(sesion, pedido_id)
    r = accion(cliente, dueno, pedido_id, "reject", {"reason": "Sin stock"})
    assert (r.status_code, r.json()["status"]) == (200, "rechazado")
    evento = sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == pedido_id)).one()
    assert evento.detail == {"reason": "Sin stock"}


def test_rechazar_sin_motivo_tambien_funciona(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    assert accion(cliente, dueno_de(sesion, pedido_id), pedido_id, "reject").status_code == 200


def test_un_pedido_rechazado_ya_no_se_acepta(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    dueno = dueno_de(sesion, pedido_id)
    accion(cliente, dueno, pedido_id, "reject")
    r = accion(cliente, dueno, pedido_id, "accept")
    assert r.status_code == 409
    assert r.json()["estado_actual"] == "rechazado"


def test_saltearse_un_paso_da_409(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    r = accion(cliente, dueno_de(sesion, pedido_id), pedido_id, "ready")
    assert (r.status_code, r.json()["estado_actual"]) == (409, "recibido")


def test_un_comercio_no_toca_el_pedido_de_otro(cliente, sesion):
    mio = crear_pedido(sesion)
    ajeno = crear_pedido(sesion)
    r = accion(cliente, dueno_de(sesion, mio), ajeno, "accept")
    assert r.status_code == 404
    assert sesion.get(Order, ajeno).status == "recibido"


def test_un_cliente_no_puede_usar_las_acciones_del_comercio(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    assert accion(cliente, cliente_de(sesion, pedido_id), pedido_id, "accept").status_code == 403


def test_sin_sesion_no_hay_acciones(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    assert cliente.post(f"/merchant/orders/{pedido_id}/accept").status_code == 401


def test_el_tablero_puede_filtrar_por_estado(cliente, sesion):
    nuevo = crear_pedido(sesion)
    dueno = dueno_de(sesion, nuevo)
    r = cliente.get("/orders?status=recibido", headers=cabecera(dueno.id))
    assert [p["id"] for p in r.json()] == [str(nuevo)]
    assert cliente.get("/orders?status=listo", headers=cabecera(dueno.id)).json() == []
    assert cliente.get("/orders?status=inventado", headers=cabecera(dueno.id)).status_code == 422


def test_el_cliente_cancela_mientras_no_se_prepare(cliente, sesion):
    for estado in ("recibido", "aceptado", "preparando"):
        pedido_id = crear_pedido(sesion, estado)
        yo = cliente_de(sesion, pedido_id)
        r = cliente.post(f"/orders/{pedido_id}/cancel", headers=cabecera(yo.id))
        assert (r.status_code, r.json()["status"]) == (200, "cancelado"), estado


def test_no_se_cancela_despues_de_preparar(cliente, sesion):
    pedido_id = crear_pedido(sesion, "listo")
    r = cliente.post(f"/orders/{pedido_id}/cancel", headers=cabecera(cliente_de(sesion, pedido_id).id))
    assert r.status_code == 409
    assert r.json()["detail"] == "Tu pedido ya está en preparación y no se puede cancelar"


def test_no_se_cancela_un_pedido_ajeno(cliente, sesion):
    mio, ajeno = crear_pedido(sesion), crear_pedido(sesion)
    r = cliente.post(f"/orders/{ajeno}/cancel", headers=cabecera(cliente_de(sesion, mio).id))
    assert r.status_code == 404
    assert sesion.get(Order, ajeno).status == "recibido"


def test_el_comercio_no_puede_cancelar_como_cliente(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    r = cliente.post(f"/orders/{pedido_id}/cancel", headers=cabecera(dueno_de(sesion, pedido_id).id))
    assert r.status_code == 403
