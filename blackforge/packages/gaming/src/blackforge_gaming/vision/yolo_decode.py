"""Pré-/post-traitement des détecteurs de type YOLOv8/YOLO11 exportés en ONNX.

Numpy pur (aucune dépendance à un runtime) pour être testable isolément.

Format de sortie géré : ``(1, 4 + nc, N)`` — boîtes ``cx, cy, w, h`` en pixels de l'entrée du
modèle, puis ``nc`` scores de classe (pas de score d'« objectness » séparé). Les sorties
d'autres familles (YOLOv5 avec objectness, modèles avec NMS intégrée) NE sont PAS gérées et
sont rejetées explicitement plutôt qu'interprétées de travers.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from blackforge_gaming.core.detection import Detection
from blackforge_gaming.core.geometry import Rect
from blackforge_gaming.core.types import Image
from blackforge_gaming.vision.nms import non_max_suppression

_PAD_VALUE = 114  # gris neutre utilisé à l'entraînement par la famille YOLO


def letterbox(
    image: Image, size_hw: tuple[int, int], cv2: Any
) -> tuple[Image, float, tuple[int, int]]:
    """Redimensionne en conservant le rapport d'aspect, complète avec du gris.

    Retourne ``(image_modèle, échelle, (pad_x, pad_y))``.
    """
    height, width = image.shape[:2]
    target_h, target_w = size_hw
    scale = min(target_w / width, target_h / height)
    new_w, new_h = max(1, round(width * scale)), max(1, round(height * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((target_h, target_w, 3), _PAD_VALUE, dtype=np.uint8)
    pad_x, pad_y = (target_w - new_w) // 2, (target_h - new_h) // 2
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    return canvas, scale, (pad_x, pad_y)


def to_model_input(letterboxed_bgr: Image) -> NDArray[np.float32]:
    """BGR HxWx3 uint8 → RGB NCHW float32 dans [0, 1]."""
    rgb = letterboxed_bgr[:, :, ::-1]
    blob = np.ascontiguousarray(rgb.transpose(2, 0, 1), dtype=np.float32) / 255.0
    return blob[np.newaxis]


def decode_yolov8(
    output: NDArray[np.floating[Any]],
    *,
    labels: Sequence[str],
    detector_name: str,
    scale: float,
    pad: tuple[int, int],
    image_size_wh: tuple[int, int],
    conf_threshold: float,
    iou_threshold: float,
) -> list[Detection]:
    if output.ndim != 3 or output.shape[0] != 1:
        msg = f"sortie de modèle inattendue {output.shape} (attendu (1, 4+nc, N))"
        raise ValueError(msg)
    expected_rows = 4 + len(labels)
    if output.shape[1] != expected_rows:
        msg = (
            f"le modèle produit {output.shape[1]} lignes mais {len(labels)} classes déclarées "
            f"imposent {expected_rows} (format YOLOv8 : 4 + nc). Autre famille de modèle ?"
        )
        raise ValueError(msg)

    preds = output[0].T.astype(np.float64)  # (N, 4+nc)
    class_scores = preds[:, 4:]
    best_class = class_scores.argmax(axis=1)
    best_score = class_scores[np.arange(len(preds)), best_class]
    mask = best_score >= conf_threshold
    if not mask.any():
        return []
    preds, best_class, best_score = preds[mask], best_class[mask], best_score[mask]

    cx, cy, w, h = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    pad_x, pad_y = pad
    width, height = image_size_wh
    boxes = np.stack(
        [
            (cx - w / 2 - pad_x) / scale,
            (cy - h / 2 - pad_y) / scale,
            (cx + w / 2 - pad_x) / scale,
            (cy + h / 2 - pad_y) / scale,
        ],
        axis=1,
    )
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, width)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, height)

    detections: list[Detection] = []
    for class_id in np.unique(
        best_class
    ):  # NMS par classe : deux classes différentes peuvent se recouvrir
        idx = np.nonzero(best_class == class_id)[0]
        for k in non_max_suppression(boxes[idx], best_score[idx], iou_threshold):
            x1, y1, x2, y2 = (round(v) for v in boxes[idx][k])
            if x2 <= x1 or y2 <= y1:
                continue  # boîte dégénérée après recadrage
            detections.append(
                Detection(
                    label=labels[int(class_id)],
                    confidence=float(min(best_score[idx][k], 1.0)),
                    box=Rect.from_xyxy(x1, y1, x2, y2),
                    detector=detector_name,
                    score_kind="model_score",
                    attributes={"class_id": int(class_id)},
                )
            )
    detections.sort(key=lambda d: -d.confidence)
    return detections
