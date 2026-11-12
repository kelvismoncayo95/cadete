import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

from app.core.config import settings


@pytest.fixture(scope="session")
def engine() -> Engine:
    url = make_url(settings.test_db_url)
    # Freno de seguridad: los tests borran todo, así que NUNCA corren contra otra base.
    if not (url.database or "").endswith("_test"):
        pytest.exit(f"Los tests solo corren en una base que termine en _test (es: {url.database})")
    return create_engine(url)


@pytest.fixture
def base_vacia(engine: Engine) -> Engine:
    """Deja la base de pruebas vacía (con PostGIS), lista para migrar."""
    with engine.begin() as con:
        con.execute(text("DROP SCHEMA public CASCADE"))
        con.execute(text("CREATE SCHEMA public"))
        con.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    return engine
