"""Tests d'intégration sur un vrai PostgreSQL (``BLACKFORGE_TEST_DATABASE_URL``)."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, Index, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from blackforge_api.db.base import Base
from blackforge_api.db.models import Membership, Organization, User  # noqa: F401
from tests.conftest import alembic_config, make_settings, running_app

pytestmark = pytest.mark.integration

TABLES = {"organizations", "users", "memberships"}


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


async def test_readiness_and_status_with_real_database(test_database_url: str) -> None:
    async with running_app(make_settings(database_url=test_database_url)) as client:
        ready = await client.get("/readyz")
        status = await client.get("/api/v1/system/status")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "database": "ok"}
    assert status.json()["status"] == "ok"
    assert status.json()["database"] == "ok"


def test_migration_upgrade_downgrade_upgrade_cycle(blank_database: str) -> None:
    config = alembic_config(blank_database)
    engine = create_engine(blank_database)
    try:
        assert _tables(engine) == set()
        command.upgrade(config, "head")
        assert _tables(engine) == TABLES
        command.downgrade(config, "base")
        assert _tables(engine) == set()
        command.upgrade(config, "head")
        assert _tables(engine) == TABLES
    finally:
        engine.dispose()


def test_models_and_migrations_have_no_schema_drift(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_constraint_and_index_names_match_models(db_engine: Engine) -> None:
    """Alembic ne compare pas les CHECK : on vérifie les noms directement dans pg_catalog."""
    expected: set[str] = set()
    for table in Base.metadata.tables.values():
        expected.update(str(c.name) for c in table.constraints if c.name is not None)
        expected.update(str(i.name) for i in table.indexes if isinstance(i, Index) and i.name)
    with db_engine.connect() as connection:
        constraints = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE connamespace = 'public'::regnamespace"
                )
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
        }
    actual = (constraints | indexes) - {"alembic_version_pkc"}
    assert actual == expected


def _new_org(connection: object, slug: str = "acme") -> str:
    row = connection.execute(  # type: ignore[attr-defined]
        text("INSERT INTO organizations (name, slug) VALUES ('Acme', :slug) RETURNING id"),
        {"slug": slug},
    ).scalar_one()
    return str(row)


def _new_user(connection: object, email: str = "ada@example.com") -> str:
    row = connection.execute(  # type: ignore[attr-defined]
        text("INSERT INTO users (email) VALUES (:email) RETURNING id"), {"email": email}
    ).scalar_one()
    return str(row)


def test_organization_slug_must_be_unique_and_well_formed(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        _new_org(connection)
        with pytest.raises(IntegrityError):
            _new_org(connection)  # doublon
    for bad in ("Acme", "-acme", "acme-", "ac me", "a--b", ""):
        with db_engine.connect() as connection, pytest.raises(IntegrityError):
            _new_org(connection, slug=bad)


def test_user_email_is_unique_case_insensitively(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        _new_user(connection, "Ada@Example.com")
        with pytest.raises(IntegrityError):
            _new_user(connection, "ada@example.COM")


def test_membership_role_and_uniqueness_are_enforced(db_engine: Engine) -> None:
    insert = text("INSERT INTO memberships (organization_id, user_id, role) VALUES (:o, :u, :r)")
    with db_engine.connect() as connection:
        org, user = _new_org(connection), _new_user(connection)
        connection.execute(insert, {"o": org, "u": user, "r": "owner"})
        with pytest.raises(IntegrityError):
            connection.execute(insert, {"o": org, "u": user, "r": "member"})  # doublon
    with db_engine.connect() as connection:
        org, user = _new_org(connection), _new_user(connection)
        with pytest.raises(IntegrityError):
            connection.execute(insert, {"o": org, "u": user, "r": "superadmin"})


def test_deleting_an_organization_cascades_to_memberships(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        org, user = _new_org(connection), _new_user(connection)
        connection.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role) VALUES (:o, :u, 'member')"
            ),
            {"o": org, "u": user},
        )
        connection.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
        remaining = connection.execute(text("SELECT count(*) FROM memberships")).scalar_one()
        assert remaining == 0
