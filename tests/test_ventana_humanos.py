from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import DispatchOffer, Order, OrderEvent, User
from app.seed import seed_demo
from app.services.demo import MARCA
from app.services.dispatch import despachar_pedido
from tests.helpers import crear_pedido, punto

LAT, LON = -34.90, -56.15


@pytest.fixture
def demo(sesion, monkeypatch):
    """La demo: Rosa es la repartidora humana prioritaria y los humanos tienen 90 s antes que los simulados."""
    monkeypatch.setattr(settings, "repartidores_prioritarios", "rosa")
    monkeypatch.setattr(settings, "espera_humanos_s", 90)
    seed_demo(sesion)
    return sesion


def courier_de(sesion, nombre):
    from app.models import Courier

    return sesion.scalar(select(Courier).join(User).where(User.username == nombre))


def colocar(sesion, nombre, lat, lon, estado="available"):
    c = courier_de(sesion, nombre)
    c.last_location, c.status = punto(lon, lat), estado
    sesion.commit()
    return c


def pedido_listo(sesion, notas=None, hace_s=0):
    pedido_id = crear_pedido(sesion, "listo")
    sesion.get(Order, pedido_id).notes = notas
    sesion.add(OrderEvent(order_id=pedido_id, from_status="preparando", to_status="listo",
                          created_at=datetime.now(timezone.utc) - timedelta(seconds=hace_s)))
    sesion.commit()
    return pedido_id


def _nombre(sesion, oferta):
    from app.models import Courier

    return sesion.scalar(select(User.username).join(Courier, Courier.user_id == User.id).where(Courier.id == oferta.courier_id))


def test_un_pedido_humano_espera_a_los_repartidores_humanos_antes_de_ofrecerse_a_los_simulados(demo):
    colocar(demo, "luis", LAT + 0.001, LON)                    # simulado, muy cerca
    colocar(demo, "rosa", LAT + 0.0135, LON, estado="offline")  # la humana todavía no se conectó
    pedido_id = pedido_listo(demo, notas="[demo]", hace_s=5)
    assert despachar_pedido(demo, pedido_id) is None            # dentro de la ventana: no se le ofrece a Luis


def test_pasada_la_ventana_se_le_ofrece_a_los_simulados(demo):
    colocar(demo, "luis", LAT + 0.001, LON)
    pedido_id = pedido_listo(demo, notas="[demo]", hace_s=100)
    oferta = despachar_pedido(demo, pedido_id)
    demo.commit()
    assert oferta is not None and _nombre(demo, oferta) == "luis"


def test_si_la_humana_se_conecta_dentro_de_la_ventana_recibe_la_oferta_aunque_haya_alguien_mas_cerca(demo):
    colocar(demo, "luis", LAT + 0.001, LON)
    colocar(demo, "rosa", LAT + 0.0135, LON)                    # más lejos, pero humana y disponible
    pedido_id = pedido_listo(demo, notas="[demo]", hace_s=5)
    oferta = despachar_pedido(demo, pedido_id)
    demo.commit()
    assert _nombre(demo, oferta) == "rosa"


def test_los_pedidos_simulados_no_esperan(demo):
    colocar(demo, "luis", LAT + 0.001, LON)
    pedido_id = pedido_listo(demo, notas=MARCA, hace_s=1)       # los atiende el simulador de punta a punta
    oferta = despachar_pedido(demo, pedido_id)
    demo.commit()
    assert _nombre(demo, oferta) == "luis"


def test_sin_configuracion_de_demo_no_hay_ventana(sesion, monkeypatch):
    """En la vida real (sin repartidores prioritarios) el comportamiento es el normal."""
    monkeypatch.setattr(settings, "repartidores_prioritarios", "")
    monkeypatch.setattr(settings, "espera_humanos_s", 90)
    seed_demo(sesion)
    colocar(sesion, "luis", LAT + 0.001, LON)
    pedido_id = pedido_listo(sesion, notas="[demo]", hace_s=1)
    assert despachar_pedido(sesion, pedido_id) is not None
