from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from blackforge_api.core.config import Settings
from blackforge_api.main import create_app

API_DIR = Path(__file__).resolve().parents[1]

# Adresse sur laquelle rien n'écoute : prouve qu'une route ne dépend pas de la base.
UNREACHABLE_DB = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucune variable BLACKFORGE_* de l'environnement du développeur ne doit fausser un test."""
    for name in [key for key in os.environ if key.startswith("BLACKFORGE_")]:
        if name != "BLACKFORGE_TEST_DATABASE_URL":
            monkeypatch.delenv(name)


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": UNREACHABLE_DB,
        "rate_limit_per_minute": 0,
        "cors_origins": ["http://allowed.example"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


type Configure = Callable[[FastAPI], None]


@asynccontextmanager
async def running_app(
    settings: Settings, configure: Configure | None = None
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    if configure is not None:
        configure(app)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, client=("203.0.113.7", 50000))
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


# --------------------------------------------------------------------------- base réelle


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("BLACKFORGE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("BLACKFORGE_TEST_DATABASE_URL non défini (tests d'intégration ignorés)")
    database_name = url.rsplit("/", 1)[-1].split("?")[0]
    if not database_name.endswith("_test"):
        # Garde-fou : ces tests détruisent et recréent le schéma.
        pytest.exit(f"Refus de toucher la base {database_name!r} : son nom doit finir par _test")
    return url


def alembic_config(url: str) -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    config.attributes["database_url"] = url
    return config


def _recreate_public_schema(url: str) -> None:
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    """Schéma reconstruit de zéro par les migrations, une fois par session de tests.

    Évite qu'un état résiduel d'un run précédent masque un défaut de migration.
    """
    _recreate_public_schema(test_database_url)
    command.upgrade(alembic_config(test_database_url), "head")
    return test_database_url


@pytest.fixture
def db_engine(migrated_database: str) -> Iterator[Engine]:
    """Base de test migrée à la dernière révision."""
    engine = create_engine(migrated_database)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def blank_database(test_database_url: str) -> Iterator[str]:
    """Base de test vide (schéma public recréé) ; la remet à jour à la fin."""
    _recreate_public_schema(test_database_url)
    try:
        yield test_database_url
    finally:
        command.upgrade(alembic_config(test_database_url), "head")
