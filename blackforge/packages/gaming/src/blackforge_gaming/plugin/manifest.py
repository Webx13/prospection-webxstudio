"""Manifeste d'un plugin de jeu (``plugin.json``).

Le manifeste décrit : identité du jeu, plateformes, version, capacités, APIs, méthodes de capture,
actions permises, permissions requises, limites d'utilisation, autorisation d'automatiser, et le
profil de vision. Structure validée strictement : champ inconnu = refus, valeur hors vocabulaire = refus.

La CONFORMITÉ (anti-cheat, multijoueur, cohérence permissions/actions…) est évaluée séparément par
``policy.evaluate_policy`` : un manifeste structurellement valide peut quand même être refusé.
"""

from __future__ import annotations

import re
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from blackforge_gaming.plugin.profile import VisionProfile
from blackforge_gaming.plugin.vocab import (
    ActionType,
    AntiCheat,
    ApiKind,
    AuthorizationKind,
    Autonomy,
    CaptureMethod,
    GameCapability,
    GameMode,
    Permission,
    Platform,
)

MANIFEST_VERSION: Final = 1
_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*){1,5}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GameInfo(_Strict):
    title: str = Field(min_length=1, max_length=120)
    publisher: str | None = Field(default=None, max_length=120)
    platforms: tuple[Platform, ...] = Field(min_length=1)
    mode: GameMode
    competitive: bool = False
    anti_cheat: AntiCheat

    @field_validator("platforms")
    @classmethod
    def _unique_platforms(cls, value: tuple[Platform, ...]) -> tuple[Platform, ...]:
        if len(set(value)) != len(value):
            msg = "plateformes en double"
            raise ValueError(msg)
        return value


class Authorization(_Strict):
    """Pourquoi automatiser ce jeu est légitime. Déclaratif : BLACKFORGE ne peut pas le vérifier."""

    kind: AuthorizationKind
    evidence: str | None = Field(default=None, max_length=500)  # URL, référence de licence, CGU…


class ApiSpec(_Strict):
    name: str = Field(min_length=1, max_length=80)
    kind: ApiKind
    url: str | None = Field(default=None, max_length=300)


class ActionSpec(_Strict):
    type: ActionType
    max_per_minute: int = Field(ge=1, le=300)
    # En mode supervisé, l'utilisateur doit valider chaque action de ce type.
    confirm_in_supervised: bool = True


class Limits(_Strict):
    max_session_seconds: int = Field(ge=60, le=4 * 3600)
    max_fps: float = Field(gt=0, le=60)
    max_actions_per_minute: int = Field(ge=0, le=300)
    autonomous_allowed: bool = False
    default_autonomy: Autonomy = Autonomy.SUPERVISED


class PluginManifest(_Strict):
    manifest_version: Literal[1]
    id: str = Field(max_length=100)
    name: str = Field(min_length=1, max_length=120)
    version: str
    publisher: str = Field(min_length=1, max_length=120)  # auteur du PLUGIN (pas forcément du jeu)
    description: str = Field(default="", max_length=1000)
    game: GameInfo
    authorization: Authorization
    capabilities: tuple[GameCapability, ...] = ()
    apis: tuple[ApiSpec, ...] = ()
    capture_methods: tuple[CaptureMethod, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    permissions: tuple[Permission, ...] = ()
    limits: Limits
    vision: VisionProfile = VisionProfile()
    # Empreinte SHA-256 de chaque fichier référencé (gabarits, modèles) : intégrité vérifiée au chargement.
    files: dict[str, str] = Field(default_factory=dict, max_length=256)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _PLUGIN_ID.fullmatch(value):
            msg = "id attendu au format 'editeur.nom-du-jeu' (minuscules, chiffres, tirets, points)"
            raise ValueError(msg)
        return value

    @field_validator("version")
    @classmethod
    def _valid_version(cls, value: str) -> str:
        if not _SEMVER.fullmatch(value):
            msg = "version attendue au format X.Y.Z"
            raise ValueError(msg)
        return value

    @field_validator("capabilities", "capture_methods", "permissions", mode="after")
    @classmethod
    def _no_duplicates(cls, value: object) -> object:
        if isinstance(value, tuple) and len(set(value)) != len(value):
            msg = "valeurs en double"
            raise ValueError(msg)
        return value

    @field_validator("actions")
    @classmethod
    def _unique_actions(cls, value: tuple[ActionSpec, ...]) -> tuple[ActionSpec, ...]:
        types = [a.type for a in value]
        if len(set(types)) != len(types):
            msg = "un type d'action ne peut être déclaré qu'une fois"
            raise ValueError(msg)
        return value

    @field_validator("files")
    @classmethod
    def _valid_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            if not _SHA256.fullmatch(digest):
                msg = f"empreinte invalide pour {path!r} (SHA-256 hexadécimal minuscule attendu)"
                raise ValueError(msg)
        return value
