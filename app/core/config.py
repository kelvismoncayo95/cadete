from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída de variables de entorno (o del .env en local)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "cadete"
    postgres_password: str = ""
    postgres_db: str = "cadete"
    # Desde tu PC la base se ve en el puerto 5433; dentro de Docker, en postgres:5432.
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    redis_url: str = "redis://localhost:6380/0"
    test_redis_url: str = "redis://localhost:6380/15"

    # Seguridad. El secreto NUNCA va en el código: viene del .env o del entorno.
    jwt_secret: str = ""
    jwt_expire_minutes: int = 60
    bcrypt_rounds: int = 12
    login_max_intentos: int = 10
    login_ventana_segundos: int = 60

    # Reglas de negocio (PRD sección 7). El envío es fijo: $60 = 6000 centavos.
    envio_cents: int = 6000
    pedidos_max_por_minuto: int = 10
    pedidos_ventana_segundos: int = 60

    # Despacho (PRD sección 7)
    oferta_segundos: int = 30
    max_ofertas_por_pedido: int = 5
    aviso_sin_repartidor_minutos: int = 10

    # Rutas por calles (OSRM). Si no responde, se usa línea recta como respaldo.
    osrm_url: str = "http://localhost:5001"
    osrm_timeout_s: float = 2.0
    velocidad_estimada_kmh: float = 30.0   # solo para el respaldo en línea recta
    # La demo corre acelerada (el simulador va más rápido que un repartidor real): el tiempo estimado
    # se divide por este factor para que coincida con lo que se ve en el mapa. En la vida real: 1.
    aceleracion_demo: float = 1.0
    # Un destino o una posición a más de esto de una calle se rechaza (por ejemplo, en el agua).
    max_distancia_a_calle_m: float = 150.0

    # Demo: repartidores «humanos» (los que maneja una persona, p. ej. "rosa") que reciben las ofertas primero,
    # para que quien visita la demo pueda probar el rol de repartidor aunque haya repartidores simulados.
    # Varios nombres separados por coma. Vacío = sin prioridad (comportamiento real).
    repartidores_prioritarios: str = ""
    # Demo: un pedido que atiende una persona (no simulado) espera esto antes de ofrecerse a los repartidores
    # simulados, para darle tiempo a la persona de conectarse como repartidora. 0 = sin espera.
    espera_humanos_s: int = 0

    # Entrega y pagos (juguete). El GPS real tiene un error de 5 a 10 m y la moto queda pegada a la calle,
    # por eso el radio de llegada no puede ser de 2 m: 25 m.
    radio_llegada_m: float = 25.0
    pago_base_repartidor_cents: int = 4000       # $40 por pedido
    pago_por_km_repartidor_cents: int = 1500     # $15 por km (el viaje al comercio también se paga)
    comision_comercio_pct: int = 10              # la plataforma se queda con el 10 % de los productos

    database_url: str | None = None
    test_database_url: str | None = None

    @property
    def prioritarios(self) -> set[str]:
        return {n.strip() for n in self.repartidores_prioritarios.split(",") if n.strip()}

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def test_db_url(self) -> str:
        if self.test_database_url:
            return self.test_database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}_test"
        )


settings = Settings()
