from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Courier, DispatchOffer, Merchant, Order, OrderEvent, User
from app.services.dispatch import despachar_pedido
from tests.helpers import (
    cabecera, crear_cliente, crear_comercio, crear_pedido, cuerpo_pedido, repartidor_en,
)

LAT, LON = -34.90, -56.15


def con_oferta(sesion, estado="listo"):
    pedido_id = crear_pedido(sesion, estado)
    rep = repartidor_en(sesion, LAT + 0.0045, LON)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    return pedido_id, rep, oferta


def test_el_repartidor_ve_sus_ofertas_pendientes(cliente, sesion):
    pedido_id, rep, oferta = con_oferta(sesion)
    otro = repartidor_en(sesion, LAT + 0.5, LON)  # lejos: no recibe nada
    r = cliente.get("/courier/offers", headers=cabecera(rep.user_id))
    assert r.status_code == 200
    (o,) = r.json()
    assert o["id"] == str(oferta.id) and o["order_id"] == str(pedido_id)
    assert o["merchant_name"].endswith("(demo)") and o["delivery_address"] == "Calle 2"
    assert 480 <= o["distance_m"] <= 520
    assert o["pay_cents"] >= 4000 and o["delivery_m"] > 0   # base + km (retiro y entrega)
    assert 0 < o["seconds_left"] <= 30
    assert cliente.get("/courier/offers", headers=cabecera(otro.user_id)).json() == []


def test_aceptar_por_la_api(cliente, sesion):
    pedido_id, rep, oferta = con_oferta(sesion)
    r = cliente.post(f"/courier/offers/{oferta.id}/accept", headers=cabecera(rep.user_id))
    assert (r.status_code, r.json()["status"]) == (200, "asignado")
    assert cliente.get("/courier/offers", headers=cabecera(rep.user_id)).json() == []


def test_rechazar_por_la_api(cliente, sesion):
    pedido_id, rep, oferta = con_oferta(sesion)
    r = cliente.post(f"/courier/offers/{oferta.id}/reject", headers=cabecera(rep.user_id))
    assert r.status_code == 200 and r.json() == {"status": "rechazada"}


def test_responder_tarde_por_la_api(cliente, sesion):
    pedido_id, rep, oferta = con_oferta(sesion)
    sesion.get(DispatchOffer, oferta.id).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    sesion.commit()
    r = cliente.post(f"/courier/offers/{oferta.id}/accept", headers=cabecera(rep.user_id))
    assert r.status_code == 409
    assert r.json()["detail"] == "No respondiste a tiempo: la oferta pasó a otro repartidor"


def test_la_oferta_de_otro_repartidor_da_404(cliente, sesion):
    pedido_id, rep, oferta = con_oferta(sesion)
    otro = repartidor_en(sesion, LAT + 0.5, LON)
    assert cliente.post(f"/courier/offers/{oferta.id}/accept", headers=cabecera(otro.user_id)).status_code == 404


def test_un_cliente_no_responde_ofertas(cliente, sesion):
    pedido_id, rep, oferta = con_oferta(sesion)
    yo = crear_cliente(sesion)
    assert cliente.post(f"/courier/offers/{oferta.id}/accept", headers=cabecera(yo.id)).status_code == 403


def asignado_a(sesion):
    pedido_id, rep, oferta = con_oferta(sesion)
    pedido = sesion.get(Order, pedido_id)
    pedido.status, pedido.courier_id = "asignado", rep.id
    sesion.get(DispatchOffer, oferta.id).status = "aceptada"
    sesion.get(Courier, rep.id).status = "busy"
    sesion.commit()
    return pedido_id, rep


def ir_a(cliente, rep, lat, lon):
    assert cliente.post("/courier/location", json={"lat": lat, "lon": lon}, headers=cabecera(rep.user_id)).status_code == 204


def test_llegar_retirar_y_entregar(cliente, sesion):
    pedido_id, rep = asignado_a(sesion)
    ir_a(cliente, rep, LAT, LON)                                   # al comercio
    r = cliente.post(f"/courier/orders/{pedido_id}/arrived", headers=cabecera(rep.user_id))
    assert (r.status_code, r.json()["status"]) == (200, "en_comercio")
    r = cliente.post(f"/courier/orders/{pedido_id}/picked-up", headers=cabecera(rep.user_id))
    assert (r.status_code, r.json()["status"]) == (200, "en_camino")
    ir_a(cliente, rep, LAT, -56.16)                                # a la casa del cliente
    r = cliente.post(f"/courier/orders/{pedido_id}/delivered", headers=cabecera(rep.user_id))
    assert (r.status_code, r.json()["status"]) == (200, "entregado")
    sesion.expire_all()
    assert sesion.get(Courier, rep.id).status == "available"


def test_no_se_puede_entregar_sin_haber_retirado(cliente, sesion):
    pedido_id, rep = asignado_a(sesion)
    r = cliente.post(f"/courier/orders/{pedido_id}/delivered", headers=cabecera(rep.user_id))
    assert (r.status_code, r.json()["estado_actual"]) == (409, "asignado")


def test_un_repartidor_no_toca_el_pedido_de_otro(cliente, sesion):
    pedido_id, rep = asignado_a(sesion)
    otro = repartidor_en(sesion, LAT + 0.5, LON)
    assert cliente.post(f"/courier/orders/{pedido_id}/arrived", headers=cabecera(otro.user_id)).status_code == 404


def test_al_marcar_listo_el_comercio_dispara_la_oferta(cliente, sesion):
    pedido_id = crear_pedido(sesion, "preparando")
    rep = repartidor_en(sesion, LAT + 0.0045, LON)
    dueno = sesion.get(User, sesion.get(Merchant, sesion.get(Order, pedido_id).merchant_id).user_id)
    r = cliente.post(f"/merchant/orders/{pedido_id}/ready", headers=cabecera(dueno.id))
    assert r.status_code == 200
    (oferta,) = sesion.scalars(select(DispatchOffer).where(DispatchOffer.order_id == pedido_id)).all()
    assert oferta.courier_id == rep.id and oferta.status == "pendiente"


def test_recorrido_completo_de_un_pedido(cliente, sesion):
    """Del clic en «Confirmar» hasta «entregado», pasando por los tres actores."""
    comercio, (pizza, _) = crear_comercio(sesion)
    dueno = sesion.get(User, comercio.user_id)
    yo = crear_cliente(sesion)
    rep = repartidor_en(sesion, LAT + 0.0045, LON)

    creado = cliente.post(
        "/orders", json=cuerpo_pedido(comercio, [(pizza, 2)]),
        headers={**cabecera(yo.id), "Idempotency-Key": "recorrido-1"},
    )
    assert creado.status_code == 201
    pedido_id = creado.json()["id"]
    for accion in ("accept", "preparing", "ready"):
        assert cliente.post(f"/merchant/orders/{pedido_id}/{accion}", headers=cabecera(dueno.id)).status_code == 200

    (oferta,) = cliente.get("/courier/offers", headers=cabecera(rep.user_id)).json()
    assert cliente.post(f"/courier/offers/{oferta['id']}/accept", headers=cabecera(rep.user_id)).status_code == 200
    ir_a(cliente, rep, LAT, LON)
    assert cliente.post(f"/courier/orders/{pedido_id}/arrived", headers=cabecera(rep.user_id)).status_code == 200
    assert cliente.post(f"/courier/orders/{pedido_id}/picked-up", headers=cabecera(rep.user_id)).status_code == 200
    ir_a(cliente, rep, -34.90, -56.16)                             # la casa del cliente (el destino de cuerpo_pedido)
    assert cliente.post(f"/courier/orders/{pedido_id}/delivered", headers=cabecera(rep.user_id)).status_code == 200

    final = cliente.get(f"/orders/{pedido_id}", headers=cabecera(yo.id)).json()
    assert final["status"] == "entregado" and final["courier_id"] == str(rep.id)
    import uuid

    eventos = sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == uuid.UUID(pedido_id)).order_by(OrderEvent.id)).all()
    assert [e.to_status for e in eventos] == [
        "recibido", "aceptado", "preparando", "listo", "asignado", "en_comercio", "en_camino", "entregado",
    ]
