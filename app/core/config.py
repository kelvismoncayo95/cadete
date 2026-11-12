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
