import uuid

from tests.helpers import cabecera, crear_cliente, crear_comercio


def test_lista_solo_los_comercios_abiertos(cliente, sesion):
    abierto, _ = crear_comercio(sesion)
    crear_comercio(sesion, abierto=False)
    yo = crear_cliente(sesion)
    r = cliente.get("/merchants", headers=cabecera(yo.id))
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [str(abierto.id)]
    assert r.json()[0]["lat"] == -34.90 and r.json()[0]["lon"] == -56.15


def test_lista_los_productos_disponibles_del_comercio(cliente, sesion):
    comercio, productos = crear_comercio(sesion)
    productos[1].is_available = False
    sesion.commit()
    yo = crear_cliente(sesion)
    r = cliente.get(f"/merchants/{comercio.id}/products", headers=cabecera(yo.id))
    assert [p["name"] for p in r.json()] == ["Pizza"]
    assert r.json()[0]["price_cents"] == 15000


def test_comercio_inexistente_da_404(cliente, sesion):
    yo = crear_cliente(sesion)
    r = cliente.get(f"/merchants/{uuid.uuid4()}/products", headers=cabecera(yo.id))
    assert r.status_code == 404


def test_el_catalogo_pide_iniciar_sesion(cliente):
    assert cliente.get("/merchants").status_code == 401
