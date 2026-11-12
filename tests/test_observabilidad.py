import json
import logging

import pytest

from app.core.observability import JsonFormatter, metricas, request_id_var
from app.models import User
from app.services.heartbeat import edad_s, latir
from app.worker.main import ciclo
from tests.helpers import cabecera, crear_cliente, crear_pedido


@pytest.fixture(autouse=True)
def metricas_limpias():
    metricas.reiniciar()
    yield


def valor(texto: str, linea: str) -> float:
    for fila in texto.splitlines():
        if fila.startswith(linea + " "):
            return float(fila.rsplit(" ", 1)[1])
    raise AssertionError(f"no está la métrica: {linea}\n{texto[:600]}")


def test_cada_respuesta_trae_un_id_de_peticion(cliente):
    r = cliente.get("/health")
    assert len(r.headers["X-Request-ID"]) >= 8


def test_si_llega_un_id_de_peticion_se_respeta(cliente):
    r = cliente.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"


def test_los_logs_son_json_con_el_id_de_peticion():
    registro = logging.LogRecord("cadete.http", logging.INFO, __file__, 1, "http", None, None)
    registro.datos = {"metodo": "GET", "ruta": "/health", "estado": 200, "ms": 3.2}
    token = request_id_var.set("req-1")
    try:
        linea = JsonFormatter().format(registro)
    finally:
        request_id_var.reset(token)
    d = json.loads(linea)
    assert d["level"] == "INFO" and d["request_id"] == "req-1"
    assert d["ruta"] == "/health" and d["estado"] == 200 and "ts" in d


def test_cada_peticion_se_registra_en_el_log(cliente, caplog):
    with caplog.at_level(logging.INFO, logger="cadete.http"):
        cliente.get("/merchants")   # sin sesión: 401
    registros = [r for r in caplog.records if r.name == "cadete.http"]
    assert registros and registros[-1].datos["ruta"] == "/merchants" and registros[-1].datos["estado"] == 401


def test_las_comprobaciones_de_salud_no_ensucian_el_log(cliente, caplog):
    with caplog.at_level(logging.INFO, logger="cadete.http"):
        cliente.get("/health")
        cliente.get("/metrics")
    assert [r for r in caplog.records if r.name == "cadete.http"] == []


def test_metrics_cuenta_las_peticiones_por_ruta_y_estado(cliente):
    cliente.get("/health")
    cliente.get("/health")
    texto = cliente.get("/metrics").text
    assert valor(texto, 'cadete_http_requests_total{method="GET",route="/health",status="200"}') == 2
    assert "# TYPE cadete_http_requests_total counter" in texto


def test_metrics_usa_la_plantilla_de_la_ruta_y_no_el_id(cliente, sesion):
    pedido_id = crear_pedido(sesion)
    dueno = sesion.get(User, sesion.get(__import__("app.models", fromlist=["Order"]).Order, pedido_id).customer_user_id)
    cliente.get(f"/orders/{pedido_id}", headers=cabecera(dueno.id))
    texto = cliente.get("/metrics").text
    assert 'route="/orders/{order_id}"' in texto
    assert str(pedido_id) not in texto   # sin ids en las etiquetas: evita explotar la cantidad de series


def test_metrics_muestra_pedidos_y_repartidores_por_estado(cliente, sesion):
    from tests.helpers import repartidor_en

    crear_pedido(sesion, "recibido")
    crear_pedido(sesion, "recibido")
    crear_pedido(sesion, "listo")
    repartidor_en(sesion, -34.9, -56.15)
    texto = cliente.get("/metrics").text
    assert valor(texto, 'cadete_orders{status="recibido"}') == 2
    assert valor(texto, 'cadete_orders{status="listo"}') == 1
    assert valor(texto, 'cadete_orders{status="entregado"}') == 0   # los estados sin pedidos también aparecen
    assert valor(texto, 'cadete_couriers{status="available"}') == 1


def test_el_latido_se_guarda_y_se_mide(redis_test):
    assert edad_s(redis_test, "worker") is None
    latir(redis_test, "worker")
    assert 0 <= edad_s(redis_test, "worker") < 3


def test_cada_vuelta_del_trabajador_late(sesion, redis_test):
    ciclo(sesion, r=redis_test)
    assert edad_s(redis_test, "worker") is not None


def sistema(cliente, sesion):
    admin = User(username="adm", password_hash="h", display_name="Admin", role="admin")
    sesion.add(admin)
    sesion.commit()
    return cliente.get("/admin/system", headers=cabecera(admin.id))


def test_el_estado_del_sistema_es_degradado_si_el_trabajador_no_late(cliente, sesion):
    r = sistema(cliente, sesion)
    assert r.status_code == 200
    d = r.json()
    assert d["checks"]["db"]["ok"] and d["checks"]["redis"]["ok"]
    assert d["checks"]["worker"]["ok"] is False
    assert d["status"] == "degradado"


def test_el_estado_del_sistema_es_ok_con_el_trabajador_vivo(cliente, sesion, redis_test):
    latir(redis_test, "worker")
    d = sistema(cliente, sesion).json()
    assert d["status"] == "ok" and d["checks"]["worker"]["ok"] is True


def test_el_estado_del_sistema_cuenta_las_alertas(cliente, sesion, redis_test):
    from app.models import AuditLog

    latir(redis_test, "worker")
    pedido_id = crear_pedido(sesion, "listo")
    sesion.add(AuditLog(action="sin_repartidor", entity="order", entity_id=str(pedido_id), detail={}))
    sesion.commit()
    assert sistema(cliente, sesion).json()["alertas"]["pedidos_sin_repartidor"] == 1


def test_el_estado_del_sistema_es_solo_del_admin(cliente, sesion):
    yo = crear_cliente(sesion)
    assert cliente.get("/admin/system", headers=cabecera(yo.id)).status_code == 403
    assert cliente.get("/admin/system").status_code == 401
