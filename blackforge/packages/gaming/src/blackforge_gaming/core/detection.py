from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from blackforge_gaming.core.geometry import Rect

# Ce que signifie ``confidence`` — la différence compte, ce ne sont PAS des probabilités :
#   similarity  : score de corrélation d'un gabarit (ex. template matching normalisé)
#   heuristic   : indice géométrique/colorimétrique défini par le détecteur (ex. taux de remplissage)
#   model_score : sortie d'un modèle appris, non calibrée
ScoreKind = Literal["similarity", "heuristic", "model_score"]

AttributeValue = float | int | str


@dataclass(frozen=True, slots=True)
class Detection:
    label: str
    confidence: float
    box: Rect  # en pixels, dans le repère de l'image analysée
    detector: str
    score_kind: ScoreKind
    track_id: int | None = None  # renseigné plus tard par le moteur de suivi
    attributes: Mapping[str, AttributeValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            msg = f"confidence doit être dans [0, 1], reçu {self.confidence}"
            raise ValueError(msg)
        if not self.label:
            msg = "label ne peut pas être vide"
            raise ValueError(msg)

    def translated(self, dx: int, dy: int) -> Detection:
        return dataclasses.replace(self, box=self.box.translated(dx, dy))
