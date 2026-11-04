"""Consentement de capture : périmètre explicite, borné dans le temps et en cadence.

Ce que c'est : une porte de contrôle appliquée par le code de capture, et une piste d'audit.
Ce que ce n'est PAS : une frontière de sécurité contre du code malveillant déjà exécuté dans le
même processus (qui pourrait fabriquer un consentement). Le consentement doit être émis par
l'application après une confirmation humaine (agent local, interface) — jamais auto-généré
par un moteur.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from blackforge_gaming.core.geometry import Rect


class ConsentError(PermissionError):
    """Consentement absent, expiré ou ne couvrant pas l'opération demandée."""


class RectModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    def to_rect(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)


def utc_now() -> datetime:
    return datetime.now(UTC)


class CaptureConsent(BaseModel):
    """Autorise la capture d'UN affichage (ou d'une zone de cet affichage), pour une durée donnée.

    Les coordonnées de ``region`` sont relatives à l'affichage, en points logiques.
    """

    model_config = ConfigDict(frozen=True)

    consent_id: str = Field(default_factory=lambda: uuid4().hex)
    purpose: str = Field(min_length=3, max_length=200)
    granted_by: str = Field(min_length=1, max_length=200)
    # 1.. = un affichage précis. 0 (« tous les écrans ») est volontairement refusé : moindre privilège.
    display_index: int = Field(ge=1)
    region: RectModel | None = None
    window_title: str | None = Field(default=None, max_length=300)  # informatif uniquement
    granted_at: datetime
    expires_at: datetime
    max_fps: float = Field(gt=0, le=240)

    @model_validator(mode="after")
    def _check_times(self) -> CaptureConsent:
        if self.granted_at.tzinfo is None or self.expires_at.tzinfo is None:
            msg = "granted_at et expires_at doivent porter un fuseau horaire"
            raise ValueError(msg)
        if self.expires_at <= self.granted_at:
            msg = "expires_at doit être postérieur à granted_at"
            raise ValueError(msg)
        return self

    @classmethod
    def grant(
        cls,
        *,
        purpose: str,
        granted_by: str,
        display_index: int,
        duration: timedelta,
        max_fps: float = 30.0,
        region: Rect | None = None,
        window_title: str | None = None,
        now: datetime | None = None,
    ) -> CaptureConsent:
        start = now or utc_now()
        return cls(
            purpose=purpose,
            granted_by=granted_by,
            display_index=display_index,
            region=RectModel(x=region.x, y=region.y, w=region.w, h=region.h) if region else None,
            window_title=window_title,
            granted_at=start,
            expires_at=start + duration,
            max_fps=max_fps,
        )

    def is_active(self, at: datetime) -> bool:
        return self.granted_at <= at < self.expires_at

    def assert_active(self, at: datetime) -> None:
        if not self.is_active(at):
            msg = f"consentement {self.consent_id[:8]} non actif (expiré ou pas encore valable)"
            raise ConsentError(msg)

    def covers(self, display_index: int, rect: Rect) -> bool:
        """Vrai si ``rect`` (relatif à l'affichage) est entièrement dans le périmètre accordé."""
        if display_index != self.display_index:
            return False
        if self.region is None:
            return True
        return self.region.to_rect().contains(rect)
