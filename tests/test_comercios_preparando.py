from tests.helpers import cabecera, crear_pedido, repartidor_en


def test_el_repartidor_ve_que_comercio_esta_preparando(cliente, sesion):
    crear_pedido(sesion, "preparando")
    rep = repartidor_en(sesion, -34.90, -56.16)
    r = cliente.get("/courier/preparing", headers=cabecera(rep.user_id))
    assert r.status_code == 200
    [c] = r.json()
    assert c["name"] == "Comercio (demo)" and c["status"] == "preparando" and c["orders"] == 1
    assert 900 < c["distance_m"] < 1200 and c["lat"] and c["lon"]


def test_un_comercio_con_pedido_listo_figura_como_listo(cliente, sesion):
    crear_pedido(sesion, "listo")
    rep = repartidor_en(sesion, -34.90, -56.16)
    [c] = cliente.get("/courier/preparing", headers=cabecera(rep.user_id)).json()
    assert c["status"] == "listo"


def test_pedidos_nuevos_o_ya_retirados_no_cuentan(cliente, sesion):
    for estado in ("recibido", "en_camino", "entregado"):
        crear_pedido(sesion, estado)
    rep = repartidor_en(sesion, -34.90, -56.16)
    assert cliente.get("/courier/preparing", headers=cabecera(rep.user_id)).json() == []


def test_solo_el_repartidor_puede_consultarlo(cliente, sesion):
    from tests.helpers import crear_cliente
    assert cliente.get("/courier/preparing", headers=cabecera(crear_cliente(sesion).id)).status_code == 403
