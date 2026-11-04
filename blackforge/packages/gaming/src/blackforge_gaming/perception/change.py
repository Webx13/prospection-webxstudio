from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from blackforge_gaming.core.types import Image

_THUMB_W, _THUMB_H = 64, 36


def _thumbnail(image: Image) -> NDArray[np.float32]:
    """Miniature en niveaux de gris (moyenne par blocs), sans dépendance à OpenCV."""
    height, width = image.shape[:2]
    block_h, block_w = max(1, height // _THUMB_H), max(1, width // _THUMB_W)
    rows, cols = height // block_h, width // block_w
    cropped = image[: rows * block_h, : cols * block_w].astype(np.float32)
    gray = cropped[:, :, 0] * 0.114 + cropped[:, :, 1] * 0.587 + cropped[:, :, 2] * 0.299
    return np.asarray(
        gray.reshape(rows, block_h, cols, block_w).mean(axis=(1, 3)), dtype=np.float32
    )


class ChangeDetector:
    """Mesure à quel point l'écran a changé depuis la dernière image ANALYSÉE.

    Le score est la différence absolue moyenne des miniatures, ramenée à [0, 1]. La référence
    n'avance que lorsque ``accept()`` est appelé (image effectivement analysée) : une dérive
    lente finit donc par dépasser le seuil au lieu d'être ignorée image après image.
    Limite : une très petite zone qui change (ex. un chiffre du score) peut rester sous le
    seuil ; abaisser le seuil ou utiliser une région d'intérêt dédiée dans ce cas.
    """

    def __init__(self, threshold: float = 0.01) -> None:
        if not 0.0 < threshold <= 1.0:
            msg = "threshold doit être dans ]0, 1]"
            raise ValueError(msg)
        self.threshold = threshold
        self._reference: NDArray[np.float32] | None = None

    def score(self, image: Image) -> float:
        thumb = _thumbnail(image)
        reference = self._reference
        if reference is None or reference.shape != thumb.shape:
            return 1.0  # pas de référence comparable (début, ou résolution modifiée)
        return float(np.abs(thumb - reference).mean() / 255.0)

    def accept(self, image: Image) -> None:
        """Retient cette image comme nouvelle référence (à appeler après l'avoir analysée)."""
        self._reference = _thumbnail(image)

    def reset(self) -> None:
        self._reference = None
