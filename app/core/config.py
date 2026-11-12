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

    # Tiempo estimado (línea recta a velocidad fija: es una estimación, y así se le dice al cliente)
    velocidad_estimada_kmh: float = 20.0

    database_url: str | None = None
    test_database_url: str | None = None

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
