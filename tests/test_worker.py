from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import DispatchOffer
from app.services.dispatch import despachar_pedido
from app.worker.main import ciclo
from tests.helpers import crear_pedido, repartidor_en

LAT, LON = -34.90, -56.15


def test_cada_vuelta_expira_ofertas_y_pasa_al_siguiente(sesion):
    pedido_id = crear_pedido(sesion, "listo")
    cerca = repartidor_en(sesion, LAT + 0.0045, LON)
    lejos = repartidor_en(sesion, LAT + 0.0135, LON)
    ahora = datetime.now(timezone.utc)
    despachar_pedido(sesion, pedido_id, ahora=ahora)
    sesion.commit()
    resultado = ciclo(sesion, ahora=ahora + timedelta(seconds=31))
    assert resultado["expiradas"] == 1
    estados = {o.courier_id: o.status for o in sesion.scalars(select(DispatchOffer))}
    assert estados == {cerca.id: "expirada", lejos.id: "pendiente"}


def test_la_vuelta_completa_reintenta_y_avisa(sesion):
    pedido_id = crear_pedido(sesion, "listo")
    assert ciclo(sesion, completo=True) == {"expiradas": 0, "ofrecidas": 0, "avisos": 0}
    repartidor_en(sesion, LAT + 0.0045, LON)
    assert ciclo(sesion, completo=True)["ofrecidas"] == 1
    assert ciclo(sesion)["expiradas"] == 0  # la vuelta corta no reintenta
