from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def non_max_suppression(
    boxes_xyxy: NDArray[np.float64], scores: NDArray[np.float64], iou_threshold: float
) -> list[int]:
    """Suppression des non-maxima. Retourne les indices conservés, du meilleur score au moins bon.

    Deux boîtes dont l'IoU dépasse ``iou_threshold`` sont considérées comme la même détection.
    """
    if len(boxes_xyxy) == 0:
        return []
    x1, y1, x2, y2 = (boxes_xyxy[:, i] for i in range(4))
    areas = np.maximum(x2 - x1, 0.0) * np.maximum(y2 - y1, 0.0)
    order = np.argsort(-scores, kind="stable")
    keep: list[int] = []
    while order.size:
        best = int(order[0])
        keep.append(best)
        if order.size == 1:
            break
        rest = order[1:]
        inter_w = np.maximum(np.minimum(x2[best], x2[rest]) - np.maximum(x1[best], x1[rest]), 0.0)
        inter_h = np.maximum(np.minimum(y2[best], y2[rest]) - np.maximum(y1[best], y1[rest]), 0.0)
        inter = inter_w * inter_h
        union = areas[best] + areas[rest] - inter
        iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
        order = rest[iou <= iou_threshold]
    return keep
