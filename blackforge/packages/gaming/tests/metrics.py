"""Métriques de détection contre une vérité terrain (germe du futur Training Lab)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from blackforge_gaming.core import Rect


@dataclass(frozen=True, slots=True)
class MatchResult:
    true_positives: int
    false_positives: int
    false_negatives: int
    mean_iou: float  # moyenne sur les paires appariées (0.0 s'il n'y en a pas)

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total else 1.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total else 1.0


def match_boxes(
    truth: Sequence[Rect], found: Sequence[Rect], iou_threshold: float = 0.5
) -> MatchResult:
    """Appariement glouton un-à-un par IoU décroissante."""
    pairs = sorted(
        ((t.iou(f), ti, fi) for ti, t in enumerate(truth) for fi, f in enumerate(found)),
        reverse=True,
    )
    used_truth: set[int] = set()
    used_found: set[int] = set()
    ious: list[float] = []
    for iou, ti, fi in pairs:
        if iou < iou_threshold:
            break
        if ti in used_truth or fi in used_found:
            continue
        used_truth.add(ti)
        used_found.add(fi)
        ious.append(iou)
    return MatchResult(
        true_positives=len(ious),
        false_positives=len(found) - len(ious),
        false_negatives=len(truth) - len(ious),
        mean_iou=sum(ious) / len(ious) if ious else 0.0,
    )
