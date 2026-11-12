import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.models import Order, OrderEvent, OrderItem
from tests.helpers import cabecera, crear_cliente, crear_comercio, cuerpo_pedido


def pedir(cliente, usuario, cuerpo, clave="clave-1"):
    cabeceras = {**cabecera(usuario.id), "Idempotency-Key": clave}
    return cliente.post("/orders", json=cuerpo, headers=cabeceras)


def contar_pedidos(sesion):
    sesion.expire_all()
    return sesion.scalar(select(func.count()).select_from(Order))


def test_crear_pedido_calcula_totales_y_guarda_todo(cliente, sesion):
    comercio, (pizza, bebida) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    r = pedir(cliente, yo, cuerpo_pedido(comercio, [(pizza, 2), (bebida, 1)]))
    assert r.status_code == 201
    pedido = r.json()
    assert pedido["status"] == "recibido"
    assert pedido["subtotal_cents"] == 2 * 15000 + 5000
    assert pedido["delivery_fee_cents"] == 6000
    assert pedido["total_cents"] == 35000 + 6000
    assert {(i["name"], i["quantity"]) for i in pedido["items"]} == {("Pizza", 2), ("Bebida", 1)}
    evento = sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == uuid.UUID(pedido["id"]))).one()
    assert (evento.from_status, evento.to_status, evento.actor_user_id) == (None, "recibido", yo.id)


def test_el_pedido_guarda_el_precio_de_ese_momento(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    pedido_id = pedir(cliente, yo, cuerpo_pedido(comercio, [(pizza, 1)])).json()["id"]
    pizza.price_cents = 99999
    pizza.name = "Pizza cara"
    sesion.commit()
    item = sesion.scalars(select(OrderItem).where(OrderItem.order_id == uuid.UUID(pedido_id))).one()
    assert (item.name_snapshot, item.unit_price_cents) == ("Pizza", 15000)


def test_confirmar_dos_veces_crea_un_solo_pedido(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    cuerpo = cuerpo_pedido(comercio, [(pizza, 1)])
    primero = pedir(cliente, yo, cuerpo)
    segundo = pedir(cliente, yo, cuerpo)
    assert primero.status_code == segundo.status_code == 201
    assert primero.json() == segundo.json()
    assert segundo.headers["Idempotent-Replay"] == "true"
    assert "Idempotent-Replay" not in primero.headers
    assert contar_pedidos(sesion) == 1


def test_misma_clave_con_otro_cuerpo_da_422(cliente, sesion):
    comercio, (pizza, bebida) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    pedir(cliente, yo, cuerpo_pedido(comercio, [(pizza, 1)]))
    r = pedir(cliente, yo, cuerpo_pedido(comercio, [(bebida, 3)]))
    assert r.status_code == 422
    assert r.json()["detail"] == "Esa clave ya se usó con otro pedido"
    assert contar_pedidos(sesion) == 1


def test_la_misma_clave_en_otro_usuario_es_otro_pedido(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    cuerpo = cuerpo_pedido(comercio, [(pizza, 1)])
    a, b = crear_cliente(sesion), crear_cliente(sesion)
    assert pedir(cliente, a, cuerpo).json()["id"] != pedir(cliente, b, cuerpo).json()["id"]
    assert contar_pedidos(sesion) == 2


def test_dos_confirmaciones_simultaneas_crean_un_solo_pedido(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    cuerpo = cuerpo_pedido(comercio, [(pizza, 1)])
    barrera = Barrier(2)

    def intentar():
        barrera.wait()
        return pedir(cliente, yo, cuerpo, clave="doble-toque")

    with ThreadPoolExecutor(2) as pool:
        respuestas = list(pool.map(lambda _: intentar(), range(2)))
    assert [r.status_code for r in respuestas] == [201, 201]
    assert respuestas[0].json()["id"] == respuestas[1].json()["id"]
    assert contar_pedidos(sesion) == 1


def test_falta_la_clave_de_idempotencia(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    r = cliente.post("/orders", json=cuerpo_pedido(comercio, [(pizza, 1)]), headers=cabecera(yo.id))
    assert r.status_code == 422
    assert "Idempotency-Key" in r.json()["detail"]


def test_carrito_vacio(cliente, sesion):
    comercio, _ = crear_comercio(sesion)
    r = pedir(cliente, crear_cliente(sesion), cuerpo_pedido(comercio, []))
    assert (r.status_code, r.json()["detail"]) == (422, "Elegí al menos un producto")


def test_cantidad_fuera_de_rango(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    for cantidad in (0, 21, -1):
        r = pedir(cliente, yo, cuerpo_pedido(comercio, [(pizza, cantidad)]), clave=f"c{cantidad}")
        assert r.status_code == 422
        assert r.json()["detail"] == "Podés pedir entre 1 y 20 unidades de cada producto"


def test_destino_fuera_de_montevideo(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    r = pedir(cliente, crear_cliente(sesion), cuerpo_pedido(comercio, [(pizza, 1)], lat=-34.48, lon=-57.85))
    assert (r.status_code, r.json()["detail"]) == (422, "Por ahora solo entregamos en Montevideo")


def test_comercio_cerrado(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion, abierto=False)
    r = pedir(cliente, crear_cliente(sesion), cuerpo_pedido(comercio, [(pizza, 1)]))
    assert (r.status_code, r.json()["detail"]) == (409, "Este comercio está cerrado ahora")


def test_producto_no_disponible_dice_cual(cliente, sesion):
    comercio, (pizza, bebida) = crear_comercio(sesion)
    bebida.is_available = False
    sesion.commit()
    r = pedir(cliente, crear_cliente(sesion), cuerpo_pedido(comercio, [(pizza, 1), (bebida, 1)]))
    assert r.status_code == 409
    assert "Bebida" in r.json()["detail"]


def test_producto_de_otro_comercio(cliente, sesion):
    comercio, _ = crear_comercio(sesion)
    _, (ajeno, _) = crear_comercio(sesion)
    r = pedir(cliente, crear_cliente(sesion), cuerpo_pedido(comercio, [(ajeno, 1)]))
    assert r.status_code == 422


def test_producto_repetido_en_el_pedido(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    r = pedir(cliente, crear_cliente(sesion), cuerpo_pedido(comercio, [(pizza, 1), (pizza, 2)]))
    assert r.status_code == 422


def test_comercio_inexistente(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    cuerpo = cuerpo_pedido(comercio, [(pizza, 1)])
    cuerpo["merchant_id"] = str(uuid.uuid4())
    assert pedir(cliente, crear_cliente(sesion), cuerpo).status_code == 404


def test_solo_los_clientes_pueden_pedir(cliente, sesion):
    from app.models import Merchant, User

    comercio, (pizza, _) = crear_comercio(sesion)
    dueno = sesion.get(User, sesion.get(Merchant, comercio.id).user_id)
    assert pedir(cliente, dueno, cuerpo_pedido(comercio, [(pizza, 1)])).status_code == 403


def test_sin_sesion_no_se_pide(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    r = cliente.post("/orders", json=cuerpo_pedido(comercio, [(pizza, 1)]), headers={"Idempotency-Key": "x"})
    assert r.status_code == 401


def test_limite_de_pedidos_por_minuto(cliente, sesion):
    comercio, (pizza, _) = crear_comercio(sesion)
    yo = crear_cliente(sesion)
    cuerpo = cuerpo_pedido(comercio, [(pizza, 1)])
    for n in range(10):
        assert pedir(cliente, yo, cuerpo, clave=f"k{n}").status_code == 201
    r = pedir(cliente, yo, cuerpo, clave="k10")
    assert r.status_code == 429
    assert "Demasiados" in r.json()["detail"]
