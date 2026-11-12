import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Courier, DispatchOffer, Order, OrderEvent
from app.services.dispatch import (
    avisar_pedidos_sin_repartidor, despachar_pedido, expirar_ofertas, reintentar_despachos,
    responder_oferta,
)
from app.services.errors import ErrorDeNegocio
from app.services.order_state import TransicionInvalida
from tests.helpers import crear_pedido, repartidor_en

LAT, LON = -34.90, -56.15  # el comercio de crear_pedido


def al_norte(grados):
    return LAT + grados, LON


def pedido_listo(sesion, *offsets):
    """Un pedido listo y repartidores disponibles a esas distancias (en grados al norte)."""
    pedido_id = crear_pedido(sesion, "listo")
    repartidores = [repartidor_en(sesion, *al_norte(g)) for g in offsets]
    return pedido_id, repartidores


def ofertas(sesion, pedido_id, estado=None):
    sesion.expire_all()
    consulta = select(DispatchOffer).where(DispatchOffer.order_id == pedido_id).order_by(DispatchOffer.offered_at, DispatchOffer.id)
    if estado:
        consulta = consulta.where(DispatchOffer.status == estado)
    return sesion.scalars(consulta).all()


def test_despachar_ofrece_al_mas_cercano_con_30_segundos(sesion):
    pedido_id, (lejos, cerca) = pedido_listo(sesion, 0.0135, 0.0045)
    ahora = datetime.now(timezone.utc)
    oferta = despachar_pedido(sesion, pedido_id, ahora=ahora)
    sesion.commit()
    assert oferta.courier_id == cerca.id
    assert oferta.status == "pendiente"
    assert 480 <= oferta.distance_m <= 520
    assert oferta.expires_at == ahora + timedelta(seconds=30)


def test_sin_repartidores_no_se_crea_oferta(sesion):
    pedido_id, _ = pedido_listo(sesion)
    assert despachar_pedido(sesion, pedido_id) is None
    assert ofertas(sesion, pedido_id) == []


def test_solo_se_despacha_un_pedido_listo(sesion):
    pedido_id = crear_pedido(sesion, "preparando")
    repartidor_en(sesion, *al_norte(0.0045))
    assert despachar_pedido(sesion, pedido_id) is None


def test_no_se_duplica_la_oferta_pendiente(sesion):
    pedido_id, _ = pedido_listo(sesion, 0.0045, 0.0135)
    despachar_pedido(sesion, pedido_id)
    sesion.commit()
    assert despachar_pedido(sesion, pedido_id) is None
    assert len(ofertas(sesion, pedido_id)) == 1


def test_aceptar_asigna_el_pedido_y_ocupa_al_repartidor(sesion):
    pedido_id, (rep,) = pedido_listo(sesion, 0.0045)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    responder_oferta(sesion, oferta.id, rep.user_id, aceptar=True)
    sesion.expire_all()
    pedido = sesion.get(Order, pedido_id)
    assert (pedido.status, pedido.courier_id) == ("asignado", rep.id)
    assert sesion.get(Courier, rep.id).status == "busy"
    assert sesion.get(DispatchOffer, oferta.id).status == "aceptada"
    assert sesion.get(DispatchOffer, oferta.id).responded_at is not None
    evento = sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == pedido_id, OrderEvent.to_status == "asignado")).one()
    assert evento.actor_user_id == rep.user_id


def test_rechazar_pasa_al_siguiente_y_no_vuelve_al_que_rechazo(sesion):
    pedido_id, (cerca, lejos) = pedido_listo(sesion, 0.0045, 0.0135)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    responder_oferta(sesion, oferta.id, cerca.user_id, aceptar=False)
    lista = ofertas(sesion, pedido_id)
    assert [(o.courier_id, o.status) for o in lista] == [(cerca.id, "rechazada"), (lejos.id, "pendiente")]
    # El que rechazó sigue disponible, pero este pedido no se le ofrece de nuevo.
    assert sesion.get(Courier, cerca.id).status == "available"
    assert reintentar_despachos(sesion) == 0


def test_una_oferta_vencida_pasa_al_siguiente(sesion):
    pedido_id, (cerca, lejos) = pedido_listo(sesion, 0.0045, 0.0135)
    ahora = datetime.now(timezone.utc)
    despachar_pedido(sesion, pedido_id, ahora=ahora)
    sesion.commit()
    assert expirar_ofertas(sesion, ahora=ahora + timedelta(seconds=10)) == 0  # todavía vigente
    assert expirar_ofertas(sesion, ahora=ahora + timedelta(seconds=31)) == 1
    lista = ofertas(sesion, pedido_id)
    assert [(o.courier_id, o.status) for o in lista] == [(cerca.id, "expirada"), (lejos.id, "pendiente")]


def test_responder_tarde_da_409_y_marca_la_oferta_vencida(sesion):
    pedido_id, (rep,) = pedido_listo(sesion, 0.0045)
    ahora = datetime.now(timezone.utc)
    oferta = despachar_pedido(sesion, pedido_id, ahora=ahora)
    sesion.commit()
    with pytest.raises(ErrorDeNegocio) as error:
        responder_oferta(sesion, oferta.id, rep.user_id, aceptar=True, ahora=ahora + timedelta(seconds=31))
    assert error.value.status_code == 409
    assert error.value.detalle == "No respondiste a tiempo: la oferta pasó a otro repartidor"
    assert ofertas(sesion, pedido_id)[0].status == "expirada"
    assert sesion.get(Order, pedido_id).status == "listo"


def test_una_oferta_ajena_no_existe_para_otro_repartidor(sesion):
    pedido_id, (uno, otro) = pedido_listo(sesion, 0.0045, 0.0135)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    with pytest.raises(ErrorDeNegocio) as error:
        responder_oferta(sesion, oferta.id, otro.user_id, aceptar=True)
    assert error.value.status_code == 404


def test_una_oferta_ya_respondida_no_se_responde_de_nuevo(sesion):
    pedido_id, (rep,) = pedido_listo(sesion, 0.0045)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    responder_oferta(sesion, oferta.id, rep.user_id, aceptar=False)
    with pytest.raises(ErrorDeNegocio) as error:
        responder_oferta(sesion, oferta.id, rep.user_id, aceptar=True)
    assert error.value.status_code == 409


def test_hasta_5_ofertas_por_pedido(sesion):
    pedido_id, reps = pedido_listo(sesion, *[0.001 * n for n in range(1, 8)])  # 7 repartidores
    por_id = {r.id: r for r in reps}
    despachar_pedido(sesion, pedido_id)
    sesion.commit()
    while pendientes := ofertas(sesion, pedido_id, "pendiente"):  # todos rechazan
        responder_oferta(sesion, pendientes[0].id, por_id[pendientes[0].courier_id].user_id, aceptar=False)
    assert len(ofertas(sesion, pedido_id)) == 5
    assert reintentar_despachos(sesion) == 0  # no hay un sexto intento
    assert sesion.get(Order, pedido_id).status == "listo"


def test_si_el_pedido_ya_no_esta_listo_no_se_puede_aceptar(sesion):
    pedido_id, (rep,) = pedido_listo(sesion, 0.0045)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    sesion.get(Order, pedido_id).status = "cancelado"
    sesion.commit()
    with pytest.raises(TransicionInvalida):
        responder_oferta(sesion, oferta.id, rep.user_id, aceptar=True)
    sesion.rollback()
    assert sesion.get(Courier, rep.id).status == "available"


def test_un_repartidor_con_oferta_pendiente_no_recibe_otra(sesion):
    primero, (rep,) = pedido_listo(sesion, 0.0045)
    segundo = crear_pedido(sesion, "listo")
    assert despachar_pedido(sesion, primero) is not None
    sesion.commit()
    assert despachar_pedido(sesion, segundo) is None


def test_dos_pedidos_simultaneos_y_un_solo_repartidor(migrada, sesion):
    primero, (rep,) = pedido_listo(sesion, 0.0045)
    segundo = crear_pedido(sesion, "listo")
    barrera = threading.Barrier(2)
    errores = []

    def despachar(pedido_id):
        try:
            with Session(migrada) as s:
                barrera.wait()
                despachar_pedido(s, pedido_id)
                s.commit()
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    hilos = [threading.Thread(target=despachar, args=(p,)) for p in (primero, segundo)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []
    total = sesion.scalar(select(func.count()).select_from(DispatchOffer).where(DispatchOffer.courier_id == rep.id))
    assert total == 1


def test_reintentar_ofrece_cuando_aparece_un_repartidor(sesion):
    pedido_id, _ = pedido_listo(sesion)
    assert reintentar_despachos(sesion) == 0
    repartidor_en(sesion, *al_norte(0.0045))
    assert reintentar_despachos(sesion) == 1
    assert len(ofertas(sesion, pedido_id, "pendiente")) == 1


def test_a_los_10_minutos_sin_repartidor_se_avisa_una_sola_vez(sesion):
    pedido_id = crear_pedido(sesion, "listo")
    ahora = datetime.now(timezone.utc)
    sesion.add(OrderEvent(order_id=pedido_id, from_status="preparando", to_status="listo", created_at=ahora - timedelta(minutes=11)))
    sesion.commit()
    assert avisar_pedidos_sin_repartidor(sesion, ahora=ahora - timedelta(minutes=2)) == 0
    assert avisar_pedidos_sin_repartidor(sesion, ahora=ahora) == 1
    assert avisar_pedidos_sin_repartidor(sesion, ahora=ahora) == 0
    aviso = sesion.scalars(select(AuditLog).where(AuditLog.action == "sin_repartidor")).one()
    assert aviso.entity_id == str(pedido_id)
