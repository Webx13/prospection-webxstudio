from __future__ import annotations

import pytest
from pydantic import ValidationError

from blackforge_api.core.config import Settings
from tests.conftest import make_settings


def test_database_url_is_required() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_url_must_use_psycopg_driver() -> None:
    with pytest.raises(ValidationError, match="psycopg"):
        make_settings(database_url="postgresql://user:pw@localhost/db")


def test_database_password_never_appears_in_repr() -> None:
    settings = make_settings(database_url="postgresql+psycopg://u:s3cr3t-pw@localhost/db")
    assert "s3cr3t-pw" not in repr(settings)
    assert "s3cr3t-pw" not in str(settings)


def test_cors_origins_are_read_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKFORGE_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("BLACKFORGE_CORS_ORIGINS", "http://a.example, http://b.example ,")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://a.example", "http://b.example"]


def test_wildcard_cors_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="production"):
        make_settings(app_env="production", cors_origins=["*"])


def test_wildcard_cors_is_tolerated_outside_production() -> None:
    assert make_settings(app_env="development", cors_origins=["*"]).cors_origins == ["*"]


def test_negative_rate_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(rate_limit_per_minute=-1)
