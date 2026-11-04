"""Détection par gabarit (template matching normalisé, multi-échelle).

Adapté aux sprites, icônes et éléments d'interface dont l'apparence est connue et stable.
Limites : sensible aux rotations, aux déformations et aux changements de rendu (anti-crénelage,
couleurs) ; le coût croît avec la taille de l'image et le nombre d'échelles. ``confidence`` est
une corrélation normalisée (« similarity »), pas une probabilité.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from blackforge_gaming.core.detection import Detection
from blackforge_gaming.core.geometry import Rect
from blackforge_gaming.core.types import Image
from blackforge_gaming.vision.nms import non_max_suppression


def _is_flat(image: Image) -> bool:
    """Vrai si chaque canal est constant : la corrélation normalisée y est indéfinie.

    L'écart-type doit être calculé PAR CANAL : un aplat (24, 16, 16) a un écart-type global non nul.
    """
    return bool(image.reshape(-1, image.shape[2]).std(axis=0).max() < 1e-6)


_MAX_CANDIDATES = 2000  # borne le coût de la NMS sur une image très « bruitée »


class TemplateDetector:
    def __init__(
        self,
        *,
        name: str,
        label: str,
        template: Image,
        threshold: float = 0.85,
        scales: Sequence[float] = (1.0,),
        max_detections: int = 50,
        nms_iou: float = 0.3,
    ) -> None:
        import cv2

        self._cv2: Any = cv2
        if template.ndim != 3 or template.shape[2] != 3 or template.dtype != np.uint8:
            msg = "le gabarit doit être une image BGR uint8 (HxWx3)"
            raise ValueError(msg)
        if _is_flat(template):
            msg = "gabarit uniforme : la corrélation normalisée est indéfinie (utilisez ColorBlobDetector)"
            raise ValueError(msg)
        if not 0.0 < threshold <= 1.0:
            msg = "threshold doit être dans ]0, 1]"
            raise ValueError(msg)
        if not scales or any(s <= 0 for s in scales):
            msg = "scales doit contenir des valeurs > 0"
            raise ValueError(msg)
        self._name = name
        self._label = label
        self._template = np.ascontiguousarray(template)
        self._threshold = threshold
        self._scales = tuple(scales)
        self._max = max_detections
        self._nms_iou = nms_iou

    @property
    def name(self) -> str:
        return self._name

    def detect(self, image: Image) -> Sequence[Detection]:
        cv2 = self._cv2
        th, tw = self._template.shape[:2]
        ih, iw = image.shape[:2]
        image = np.ascontiguousarray(image)
        boxes: list[tuple[float, float, float, float]] = []
        scores: list[float] = []
        for scale in self._scales:
            sw, sh = max(1, round(tw * scale)), max(1, round(th * scale))
            if sw > iw or sh > ih:
                continue
            tpl = self._template
            if (sw, sh) != (tw, th):
                interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                tpl = cv2.resize(self._template, (sw, sh), interpolation=interpolation)
                if _is_flat(tpl):
                    continue
            result = cv2.matchTemplate(image, tpl, cv2.TM_CCOEFF_NORMED)
            result = np.nan_to_num(result, nan=-1.0, posinf=-1.0, neginf=-1.0)
            ys, xs = np.nonzero(result >= self._threshold)
            for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
                boxes.append((x, y, x + sw, y + sh))
                scores.append(float(result[y, x]))
        if not boxes:
            return []
        boxes_arr = np.asarray(boxes, dtype=np.float64)
        scores_arr = np.asarray(scores, dtype=np.float64)
        if len(scores_arr) > _MAX_CANDIDATES:
            top = np.argsort(-scores_arr)[:_MAX_CANDIDATES]
            boxes_arr, scores_arr = boxes_arr[top], scores_arr[top]
        keep = non_max_suppression(boxes_arr, scores_arr, self._nms_iou)[: self._max]
        detections = [
            Detection(
                label=self._label,
                confidence=float(np.clip(scores_arr[i], 0.0, 1.0)),
                box=Rect.from_xyxy(*(int(v) for v in boxes_arr[i])),
                detector=self._name,
                score_kind="similarity",
            )
            for i in keep
        ]
        detections.sort(key=lambda d: (d.box.y, d.box.x))
        return detections
