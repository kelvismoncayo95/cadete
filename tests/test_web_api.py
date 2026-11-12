from datetime import datetime, timezone

from app.models import AuditLog, Courier, Merchant, Order, User
from app.seed import DEMO_PASSWORD, SIMULADOS, seed_demo
from tests.helpers import cabecera, crear_cliente, crear_pedido, crear_repartidor


def test_la_lista_de_usuarios_de_demo_es_publica_e_incluye_la_clave(cliente, sesion):
    seed_demo(sesion)
    crear_cliente(sesion)  # un usuario que NO es de la demo: no debe aparecer
    r = cliente.get("/demo/users")  # sin sesión
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["password"] == DEMO_PASSWORD
    por_rol = {}
    for u in cuerpo["users"]:
        por_rol.setdefault(u["role"], []).append(u["username"])
    assert set(por_rol["customer"]) == {"ana", "pedro"}
    assert set(por_rol["courier"]) == {"luis", "marta", "diego", "rosa"}
    assert por_rol["admin"] == ["admin"]
    assert len(por_rol["merchant"]) == 5
    assert all(not u["username"].startswith("cli_") for u in cuerpo["users"])


def test_se_marca_a_los_repartidores_que_maneja_el_simulador(cliente, sesion):
    seed_demo(sesion)
    usuarios = {u["username"]: u for u in cliente.get("/demo/users").json()["users"]}
    for nombre in SIMULADOS:
        assert usuarios[nombre]["simulated"] is True
    assert usuarios["rosa"]["simulated"] is False
    assert usuarios["ana"]["simulated"] is False


def test_el_comercio_ve_las_alertas_de_sus_pedidos_sin_repartidor(cliente, sesion):
    mio, ajeno = crear_pedido(sesion, "listo"), crear_pedido(sesion, "listo")
    for pedido_id in (mio, ajeno):
        sesion.add(AuditLog(action="sin_repartidor", entity="order", entity_id=str(pedido_id), detail={}))
    sesion.commit()
    dueno = sesion.get(User, sesion.get(Merchant, sesion.get(Order, mio).merchant_id).user_id)
    r = cliente.get("/merchant/alerts", headers=cabecera(dueno.id))
    assert r.status_code == 200
    assert r.json() == [{"order_id": str(mio), "type": "sin_repartidor"}]


def test_un_pedido_que_ya_se_asigno_deja_de_alertar(cliente, sesion):
    pedido_id = crear_pedido(sesion, "asignado")
    sesion.add(AuditLog(action="sin_repartidor", entity="order", entity_id=str(pedido_id), detail={}))
    sesion.commit()
    dueno = sesion.get(User, sesion.get(Merchant, sesion.get(Order, pedido_id).merchant_id).user_id)
    assert cliente.get("/merchant/alerts", headers=cabecera(dueno.id)).json() == []


def test_las_alertas_son_solo_del_comercio(cliente, sesion):
    yo = crear_cliente(sesion)
    assert cliente.get("/merchant/alerts", headers=cabecera(yo.id)).status_code == 403


def test_el_repartidor_consulta_su_estado_y_su_posicion(cliente, sesion):
    rep = crear_repartidor(sesion)
    r = cliente.get("/courier/status", headers=cabecera(rep.user_id))
    assert (r.status_code, r.json()) == (200, {"status": "offline", "lat": None, "lon": None})
    rep.status = "busy"
    sesion.commit()
    assert cliente.get("/courier/status", headers=cabecera(rep.user_id)).json()["status"] == "busy"
    cliente.post("/courier/location", json={"lat": -34.91, "lon": -56.15}, headers=cabecera(rep.user_id))
    r = cliente.get("/courier/status", headers=cabecera(rep.user_id)).json()
    assert (r["lat"], r["lon"]) == (-34.91, -56.15)


def test_las_paginas_de_cada_rol_se_sirven(cliente):
    for pagina in ("/", "/cliente.html", "/comercio.html", "/repartidor.html", "/admin.html", "/mapa.html"):
        r = cliente.get(pagina)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"], pagina
        assert "Datos inventados" in r.text, pagina  # aviso obligatorio en cada pantalla


def test_los_scripts_de_la_web_tienen_sintaxis_valida(tmp_path):
    """Una guarda barata: si un módulo JavaScript tiene un error de sintaxis, la pantalla queda en blanco."""
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    if shutil.which("node") is None:
        pytest.skip("Node no está instalado")
    carpeta = Path(__file__).resolve().parent.parent / "web" / "js"
    scripts = sorted(carpeta.glob("*.js"))
    assert len(scripts) >= 8
    for script in scripts:
        copia = tmp_path / (script.stem + ".mjs")   # .mjs: Node lo lee como módulo ES (usan import/export)
        copia.write_text(script.read_text())
        resultado = subprocess.run(["node", "--check", str(copia)], capture_output=True, text=True)
        assert resultado.returncode == 0, f"{script.name}: {resultado.stderr[:300]}"
