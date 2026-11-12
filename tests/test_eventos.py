import json
import threading
import time

import httpx
import pytest

from app.models import Courier, Merchant, Order, User
from app.services.events import CANAL_TODO, canal_pedido, datos_de_pedido, publicar_estado
from tests.helpers import cabecera, crear_pedido, repartidor_en

LAT, LON = -34.90, -56.15


@pytest.fixture
def escucha(redis_test):
    """Se suscribe a canales y devuelve una función que lee los mensajes publicados."""
    ps = redis_test.pubsub(ignore_subscribe_messages=True)

    def suscribir(*canales):
        ps.subscribe(*canales)
        ps.get_message(timeout=1)  # confirmación de la suscripción

    def leer(n=1):
        mensajes = []
        for _ in range(n * 20):
            m = ps.get_message(timeout=0.2)
            if m:
                mensajes.append((m["channel"], json.loads(m["data"])))
            if len(mensajes) == n:
                break
        return mensajes

    leer.suscribir = suscribir
    yield leer
    ps.close()


def pedido_con_repartidor(sesion, estado="asignado"):
    pedido_id = crear_pedido(sesion, estado)
    rep = repartidor_en(sesion, LAT + 0.0045, LON, estado="busy")
    pedido = sesion.get(Order, pedido_id)
    pedido.courier_id = rep.id
    sesion.commit()
    return pedido_id, rep


def test_los_datos_del_pedido_incluyen_estado_posiciones_y_tiempo_estimado(sesion):
    pedido_id, rep = pedido_con_repartidor(sesion)
    datos = datos_de_pedido(sesion, sesion.get(Order, pedido_id))
    assert datos["tipo"] == "estado" and datos["status"] == "asignado"
    assert datos["merchant"] == {"lat": LAT, "lon": LON}
    assert datos["courier"]["lat"] == pytest.approx(LAT + 0.0045)
    assert datos["eta_min"] >= 1


def test_sin_repartidor_no_hay_posicion_ni_tiempo_estimado(sesion):
    pedido_id = crear_pedido(sesion, "preparando")
    datos = datos_de_pedido(sesion, sesion.get(Order, pedido_id))
    assert datos["courier"] is None and datos["eta_min"] is None


def test_publicar_estado_llega_al_canal_del_pedido_y_al_general(sesion, redis_test, escucha):
    pedido_id = crear_pedido(sesion, "aceptado")
    escucha.suscribir(canal_pedido(pedido_id), CANAL_TODO)
    publicar_estado(sesion, redis_test, pedido_id)
    canales = {c for c, _ in escucha(2)}
    assert canales == {canal_pedido(pedido_id), CANAL_TODO}


def test_una_accion_del_comercio_publica_el_nuevo_estado(cliente, sesion, redis_test, escucha):
    pedido_id = crear_pedido(sesion)
    dueno = sesion.get(User, sesion.get(Merchant, sesion.get(Order, pedido_id).merchant_id).user_id)
    escucha.suscribir(canal_pedido(pedido_id))
    cliente.post(f"/merchant/orders/{pedido_id}/accept", headers=cabecera(dueno.id))
    (canal, mensaje), = escucha(1)
    assert (mensaje["tipo"], mensaje["status"]) == ("estado", "aceptado")


def test_la_cancelacion_publica_el_estado(cliente, sesion, escucha):
    pedido_id = crear_pedido(sesion)
    escucha.suscribir(canal_pedido(pedido_id))
    yo = sesion.get(Order, pedido_id).customer_user_id
    cliente.post(f"/orders/{pedido_id}/cancel", headers=cabecera(yo))
    (_, mensaje), = escucha(1)
    assert mensaje["status"] == "cancelado"


def test_enviar_posicion_con_pedido_en_curso_publica_posicion_y_tiempo(cliente, sesion, escucha):
    pedido_id, rep = pedido_con_repartidor(sesion, "en_camino")
    escucha.suscribir(canal_pedido(pedido_id), CANAL_TODO)
    cliente.post("/courier/location", json={"lat": LAT + 0.004, "lon": LON}, headers=cabecera(rep.user_id))
    por_canal = {c: m for c, m in escucha(2)}
    assert por_canal[canal_pedido(pedido_id)]["tipo"] == "posicion"
    assert por_canal[canal_pedido(pedido_id)]["eta_min"] >= 1
    assert por_canal[CANAL_TODO]["tipo"] == "repartidor"
    assert por_canal[CANAL_TODO]["courier_id"] == str(rep.id)


def test_enviar_posicion_sin_pedido_solo_llega_al_canal_general(cliente, sesion, escucha):
    rep = repartidor_en(sesion, LAT, LON)
    escucha.suscribir(CANAL_TODO)
    cliente.post("/courier/location", json={"lat": LAT, "lon": LON}, headers=cabecera(rep.user_id))
    (canal, mensaje), = escucha(1)
    assert canal == CANAL_TODO and mensaje["tipo"] == "repartidor"


def test_aceptar_retirar_y_entregar_publican_estados(cliente, sesion, escucha):
    from app.services.dispatch import despachar_pedido

    pedido_id = crear_pedido(sesion, "listo")
    rep = repartidor_en(sesion, LAT + 0.0045, LON)
    oferta = despachar_pedido(sesion, pedido_id)
    sesion.commit()
    escucha.suscribir(canal_pedido(pedido_id))
    cliente.post(f"/courier/offers/{oferta.id}/accept", headers=cabecera(rep.user_id))
    cliente.post(f"/courier/orders/{pedido_id}/picked-up", headers=cabecera(rep.user_id))
    cliente.post(f"/courier/orders/{pedido_id}/delivered", headers=cabecera(rep.user_id))
    assert [m["status"] for _, m in escucha(3)] == ["asignado", "en_camino", "entregado"]


# ---------- SSE ----------

def leer_stream(base, url, headers, destino: list, listo: threading.Event):
    """Lee un stream SSE en un hilo y guarda cada línea 'event:' y 'data:'."""
    try:
        with httpx.Client(base_url=base, timeout=10) as c, c.stream("GET", url, headers=headers) as r:
            destino.append(("status", r.status_code))
            if r.status_code != 200:
                listo.set()
                return
            for linea in r.iter_lines():
                if linea.startswith("event:") or linea.startswith("data:"):
                    destino.append((linea.split(":", 1)[0], linea.split(":", 1)[1].strip()))
                    listo.set()  # ya llegó al menos el estado inicial
    except httpx.HTTPError:
        pass  # el servidor de prueba se cerró mientras el stream seguía abierto
    finally:
        listo.set()


def abrir(base, url, headers=None):
    lineas, listo = [], threading.Event()
    hilo = threading.Thread(target=leer_stream, args=(base, url, headers or {}, lineas, listo), daemon=True)
    hilo.start()
    assert listo.wait(5), "el stream no respondió"
    return hilo, lineas


def test_el_stream_empieza_con_el_estado_actual_y_termina_al_entregar(servidor, sesion, redis_test):
    pedido_id, rep = pedido_con_repartidor(sesion, "en_camino")
    yo = sesion.get(Order, pedido_id).customer_user_id
    hilo, lineas = abrir(servidor, f"/orders/{pedido_id}/live", cabecera(yo))
    assert lineas[0] == ("status", 200)
    assert lineas[1] == ("event", "estado")
    assert json.loads(lineas[2][1])["status"] == "en_camino"

    time.sleep(0.3)  # que la suscripción esté lista
    redis_test.publish(canal_pedido(pedido_id), json.dumps({"tipo": "posicion", "order_id": str(pedido_id), "lat": LAT, "lon": LON, "eta_min": 3}))
    redis_test.publish(canal_pedido(pedido_id), json.dumps({"tipo": "estado", "order_id": str(pedido_id), "status": "entregado"}))
    hilo.join(5)
    assert not hilo.is_alive(), "el stream debe cerrarse cuando el pedido termina"
    eventos = [v for k, v in lineas if k == "event"]
    assert eventos == ["estado", "posicion", "estado"]


def test_al_reconectar_se_recibe_el_estado_actual(servidor, sesion):
    pedido_id = crear_pedido(sesion, "entregado")  # ya terminó: manda el estado y cierra
    yo = sesion.get(Order, pedido_id).customer_user_id
    hilo, lineas = abrir(servidor, f"/orders/{pedido_id}/live", cabecera(yo))
    hilo.join(5)
    assert not hilo.is_alive()
    assert json.loads(lineas[2][1])["status"] == "entregado"


def test_el_stream_de_un_pedido_ajeno_da_404(servidor, sesion):
    mio, ajeno = crear_pedido(sesion), crear_pedido(sesion)
    yo = sesion.get(Order, mio).customer_user_id
    hilo, lineas = abrir(servidor, f"/orders/{ajeno}/live", cabecera(yo))
    hilo.join(5)
    assert lineas[0] == ("status", 404)


def test_el_navegador_puede_pasar_el_token_por_la_url(servidor, sesion):
    """EventSource no permite cabeceras: se acepta ?token= solo en los streams."""
    from app.core.security import crear_token

    pedido_id = crear_pedido(sesion, "entregado")
    yo = sesion.get(Order, pedido_id).customer_user_id
    hilo, lineas = abrir(servidor, f"/orders/{pedido_id}/live?token={crear_token(yo)}")
    hilo.join(5)
    assert lineas[0] == ("status", 200)


def test_el_stream_sin_sesion_da_401(servidor, sesion):
    pedido_id = crear_pedido(sesion)
    hilo, lineas = abrir(servidor, f"/orders/{pedido_id}/live")
    hilo.join(5)
    assert lineas[0] == ("status", 401)


def test_el_stream_del_admin_empieza_con_repartidores_y_pedidos_activos(servidor, sesion):
    pedido_con_repartidor(sesion, "en_camino")
    admin = User(username="adm", password_hash="h", display_name="Admin", role="admin")
    sesion.add(admin)
    sesion.commit()
    hilo, lineas = abrir(servidor, "/admin/live", cabecera(admin.id))
    assert lineas[1] == ("event", "snapshot")
    datos = json.loads(lineas[2][1])
    assert len(datos["couriers"]) == 1 and len(datos["orders"]) == 1
    assert datos["orders"][0]["status"] == "en_camino"
    # (el stream del admin no termina solo: el hilo se cierra al terminar el test)


def test_el_stream_del_admin_es_solo_para_el_admin(servidor, sesion):
    pedido_id = crear_pedido(sesion)
    yo = sesion.get(Order, pedido_id).customer_user_id
    hilo, lineas = abrir(servidor, "/admin/live", cabecera(yo))
    hilo.join(5)
    assert lineas[0] == ("status", 403)
