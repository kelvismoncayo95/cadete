import os

# Valores solo para tests: deben fijarse ANTES de importar la app.
os.environ.setdefault("JWT_SECRET", "secreto-solo-para-tests-no-usar-en-produccion")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # bcrypt rápido en tests

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


@pytest.fixture
def migrada(engine: Engine) -> Engine:
    """Base de pruebas migrada a la última versión y SIN datos.

    Si ya está migrada, solo se vacían las tablas (mucho más rápido que recrear todo).
    """
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect

    from app.models import Base
    from tests.helpers import alembic_cfg

    tablas = [t.name for t in Base.metadata.sorted_tables]
    with engine.connect() as con:
        actual = MigrationContext.configure(con).get_current_revision()
    ultima = ScriptDirectory.from_config(alembic_cfg()).get_current_head()
    if actual == ultima and set(tablas) <= set(inspect(engine).get_table_names()):
        with engine.begin() as con:
            con.execute(text(f"TRUNCATE {', '.join(tablas)} RESTART IDENTITY CASCADE"))
        return engine

    with engine.begin() as con:
        con.execute(text("DROP SCHEMA public CASCADE"))
        con.execute(text("CREATE SCHEMA public"))
        con.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    command.upgrade(alembic_cfg(), "head")
    return engine


@pytest.fixture
def sesion(migrada: Engine):
    from sqlalchemy.orm import Session

    with Session(migrada) as s:
        yield s


@pytest.fixture
def redis_test():
    """Redis de pruebas (base 15), vacío antes de cada test."""
    import redis

    r = redis.Redis.from_url(settings.test_redis_url, decode_responses=True)
    r.flushdb()
    yield r
    r.flushdb()
    r.close()


@pytest.fixture
def cliente(migrada: Engine, redis_test):
    """Cliente HTTP de pruebas, conectado a la base y al Redis de pruebas."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    def db_de_prueba():
        with Session(migrada, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_db] = db_de_prueba
    app.dependency_overrides[get_redis] = lambda: redis_test
    yield TestClient(app)
    app.dependency_overrides.clear()
