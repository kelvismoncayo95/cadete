import threading
from itertools import product

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderEvent
from app.models.order import ESTADOS
from app.services.order_state import (
    TRANSICIONES, OrderNotFound, TransicionInvalida, cambiar_estado, puede_pasar,
)
from tests.helpers import crear_pedido

VALIDAS = [
    ("recibido", "aceptado"), ("recibido", "rechazado"), ("recibido", "cancelado"),
    ("aceptado", "preparando"), ("aceptado", "cancelado"),
    ("preparando", "listo"), ("preparando", "cancelado"),
    ("listo", "asignado"), ("asignado", "en_comercio"), ("en_comercio", "en_camino"), ("en_camino", "entregado"),
]
INVALIDAS = [par for par in product(ESTADOS, ESTADOS) if par not in VALIDAS]


def test_la_tabla_de_transiciones_cubre_todos_los_estados():
    assert set(TRANSICIONES) == set(ESTADOS)


@pytest.mark.parametrize("origen,destino", VALIDAS)
def test_transicion_valida(origen, destino):
    assert puede_pasar(origen, destino)


@pytest.mark.parametrize("origen,destino", INVALIDAS)
def test_transicion_invalida(origen, destino):
    assert not puede_pasar(origen, destino)


def test_cambiar_estado_guarda_el_nuevo_estado_y_el_historial(sesion):
    pedido_id = crear_pedido(sesion)
    cambiar_estado(sesion, pedido_id, "aceptado", detalle={"motivo": "ok"})
    sesion.commit()
    sesion.expire_all()
    assert sesion.get(Order, pedido_id).status == "aceptado"
    evento = sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == pedido_id)).one()
    assert (evento.from_status, evento.to_status) == ("recibido", "aceptado")
    assert evento.detail == {"motivo": "ok"}


def test_transicion_invalida_no_cambia_nada_ni_deja_historial(sesion):
    pedido_id = crear_pedido(sesion)
    with pytest.raises(TransicionInvalida) as error:
        cambiar_estado(sesion, pedido_id, "entregado")
    assert error.value.actual == "recibido"
    sesion.rollback()
    assert sesion.get(Order, pedido_id).status == "recibido"
    assert sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == pedido_id)).all() == []


def test_pedido_inexistente(sesion):
    import uuid

    with pytest.raises(OrderNotFound):
        cambiar_estado(sesion, uuid.uuid4(), "aceptado")


def test_recorrido_completo_deja_un_evento_por_paso(sesion):
    pedido_id = crear_pedido(sesion)
    for destino in ("aceptado", "preparando", "listo", "asignado", "en_comercio", "en_camino", "entregado"):
        cambiar_estado(sesion, pedido_id, destino)
    sesion.commit()
    eventos = sesion.scalars(
        select(OrderEvent).where(OrderEvent.order_id == pedido_id).order_by(OrderEvent.id)
    ).all()
    assert [e.to_status for e in eventos] == [
        "aceptado", "preparando", "listo", "asignado", "en_comercio", "en_camino", "entregado",
    ]


def test_dos_cambios_simultaneos_solo_uno_gana(migrada, sesion):
    """El comercio acepta y, a la vez, otro intento acepta: uno solo puede ganar."""
    for _ in range(10):
        pedido_id = crear_pedido(sesion)
        resultados: list[str] = []
        barrera = threading.Barrier(2)

        def intentar():
            with Session(migrada) as s:
                barrera.wait()
                try:
                    cambiar_estado(s, pedido_id, "aceptado")
                    s.commit()
                    resultados.append("ok")
                except TransicionInvalida:
                    s.rollback()
                    resultados.append("invalida")

        hilos = [threading.Thread(target=intentar) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        assert sorted(resultados) == ["invalida", "ok"]
        eventos = sesion.scalars(select(OrderEvent).where(OrderEvent.order_id == pedido_id)).all()
        assert len(eventos) == 1
