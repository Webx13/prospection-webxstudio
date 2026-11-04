"""Détection par couleur (espace HSV d'OpenCV : H 0-179, S 0-255, V 0-255).

Adapté aux éléments d'interface et sprites de couleur franche (barres de vie, marqueurs,
ennemis colorés). Limites : deux objets de même couleur qui se touchent fusionnent en une seule
détection ; l'éclairage/les effets qui changent la teinte dégradent la détection.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from blackforge_gaming.core.detection import Detection
from blackforge_gaming.core.geometry import Rect
from blackforge_gaming.core.types import Image

HSV = tuple[int, int, int]


class ColorBlobDetector:
    """Trouve les régions connexes dont la couleur est dans ``[hsv_lower, hsv_upper]``.

    Si ``hsv_lower[0] > hsv_upper[0]`` la plage de teinte « fait le tour » (nécessaire pour le rouge,
    à cheval sur 0/179). ``confidence`` est le taux de remplissage de la boîte englobante
    (heuristique : un rectangle plein vaut 1.0), pas une probabilité.
    """

    def __init__(
        self,
        *,
        name: str,
        label: str,
        hsv_lower: HSV,
        hsv_upper: HSV,
        min_area: int = 16,
        max_area: int | None = None,
        min_fill_ratio: float = 0.5,
    ) -> None:
        import cv2

        self._cv2: Any = cv2
        if not 0 <= hsv_lower[0] <= 179 or not 0 <= hsv_upper[0] <= 179:
            msg = "la teinte HSV doit être dans [0, 179]"
            raise ValueError(msg)
        if min_area < 1:
            msg = "min_area doit être >= 1"
            raise ValueError(msg)
        self._name = name
        self._label = label
        self._lower = hsv_lower
        self._upper = hsv_upper
        self._min_area = min_area
        self._max_area = max_area
        self._min_fill = min_fill_ratio

    @property
    def name(self) -> str:
        return self._name

    def _mask(self, image: Image) -> Any:
        cv2 = self._cv2
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        low, high = self._lower, self._upper
        if low[0] <= high[0]:
            return cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))
        first = cv2.inRange(
            hsv, np.array(low, np.uint8), np.array((179, high[1], high[2]), np.uint8)
        )
        second = cv2.inRange(hsv, np.array((0, low[1], low[2]), np.uint8), np.array(high, np.uint8))
        return cv2.bitwise_or(first, second)

    def detect(self, image: Image) -> Sequence[Detection]:
        cv2 = self._cv2
        mask = self._mask(image)
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        detections: list[Detection] = []
        for i in range(1, count):  # 0 = fond
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < self._min_area or (self._max_area is not None and area > self._max_area):
                continue
            fill = area / (w * h)
            if fill < self._min_fill:
                continue
            detections.append(
                Detection(
                    label=self._label,
                    confidence=min(fill, 1.0),
                    box=Rect(x, y, w, h),
                    detector=self._name,
                    score_kind="heuristic",
                    attributes={"area_px": area},
                )
            )
        detections.sort(key=lambda d: (d.box.y, d.box.x))
        return detections
