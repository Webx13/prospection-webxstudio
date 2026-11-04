"""Contrats entre moteurs. Chaque moteur n'en connaît que ces interfaces, jamais l'autre moteur.

Remplacer un moteur = fournir un autre objet qui respecte le protocole correspondant.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from blackforge_gaming.core.detection import Detection
from blackforge_gaming.core.frame import Frame
from blackforge_gaming.core.types import Image


@runtime_checkable
class FrameSource(Protocol):
    """Source d'images : écran, fenêtre, rejeu d'une capture enregistrée, émulateur…"""

    @property
    def source_id(self) -> str: ...

    def open(self) -> None: ...

    def read(self) -> Frame | None:
        """Prochaine image, ou ``None`` si le flux est terminé (rejeu)."""
        ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class Detector(Protocol):
    """Détecte des objets dans une image (BGR uint8). Les boîtes sont dans le repère de l'image."""

    @property
    def name(self) -> str: ...

    def detect(self, image: Image) -> Sequence[Detection]: ...
