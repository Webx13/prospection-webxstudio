"""Configuration de l'API, lue depuis l'environnement (préfixe ``BLACKFORGE_``).

Aucune valeur sensible n'a de défaut dans le code : l'URL de base de données est
obligatoire et portée par un ``SecretStr`` pour ne jamais apparaître dans un ``repr``.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# blackforge/.env — ignoré sans erreur s'il n'existe pas (cas Docker : variables injectées).
_ENV_FILE = Path(__file__).resolve().parents[5] / ".env"

_DB_SCHEME = "postgresql+psycopg://"


def package_version() -> str:
    try:
        return version("blackforge-api")
    except PackageNotFoundError:  # pragma: no cover - exécution hors installation
        return "0.0.0+unknown"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BLACKFORGE_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False
    docs_enabled: bool = True
    # Requêtes par minute et par adresse client sur /api/*. 0 désactive la limite.
    rate_limit_per_minute: int = Field(default=120, ge=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(_DB_SCHEME):
            msg = f"database_url doit commencer par {_DB_SCHEME!r} (pilote psycopg 3)"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _check_production(self) -> Self:
        if self.app_env == "production" and "*" in self.cors_origins:
            msg = "cors_origins ne peut pas contenir '*' en production"
            raise ValueError(msg)
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # database_url est lue dans l'environnement
