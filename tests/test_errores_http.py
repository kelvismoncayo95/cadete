from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import registrar_manejadores_de_error
from app.services.order_state import TransicionInvalida


def test_transicion_invalida_responde_409_con_el_estado_actual():
    app = FastAPI()
    registrar_manejadores_de_error(app)

    @app.get("/prueba")
    def prueba():
        raise TransicionInvalida("recibido", "entregado")

    respuesta = TestClient(app).get("/prueba")
    assert respuesta.status_code == 409
    assert respuesta.json()["estado_actual"] == "recibido"
    assert "recibido" in respuesta.json()["detail"]
