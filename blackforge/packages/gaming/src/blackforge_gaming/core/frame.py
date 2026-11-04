from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from blackforge_gaming.core.geometry import Rect
from blackforge_gaming.core.types import Image


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    """Une image capturée, immuable (le tableau est en lecture seule) et horodatée.

    ``pixel_scale`` : pixels physiques par point logique (2.0 sur un écran Retina). Les
    régions d'intérêt et le consentement s'expriment en points logiques ; l'image, elle, est
    en pixels physiques.
    """

    image: Image
    index: int
    captured_at_ns: int  # horloge monotone : sert à mesurer des latences, pas une date
    source_id: str
    pixel_scale: float = 1.0
    origin: tuple[int, int] = (0, 0)  # coin haut-gauche dans l'espace logique de la source
    consent_id: str | None = None

    def __post_init__(self) -> None:
        image = self.image
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            msg = f"Frame attend une image HxWx3 uint8 (BGR), reçu {image.shape} {image.dtype}"
            raise ValueError(msg)
        if image.shape[0] == 0 or image.shape[1] == 0:
            msg = "Frame: image vide"
            raise ValueError(msg)
        if self.pixel_scale <= 0:
            msg = "Frame: pixel_scale doit être > 0"
            raise ValueError(msg)
        image.setflags(write=False)

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    def crop(self, rect: Rect) -> Image:
        """Vue (sans copie) sur une zone en pixels. Lève ``ValueError`` si hors de l'image."""
        clipped = rect.clamped(self.width, self.height)
        if clipped is None:
            msg = f"Zone {rect} hors de l'image {self.width}x{self.height}"
            raise ValueError(msg)
        return self.image[clipped.y : clipped.y2, clipped.x : clipped.x2]
