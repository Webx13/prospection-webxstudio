"""Détection des capacités RÉELLES : on ne suppose jamais qu'une capture ou un backend marche."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"  # impossible à déterminer ici (ex. non testable sur ce système)
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    availability: Availability
    detail: str = ""
