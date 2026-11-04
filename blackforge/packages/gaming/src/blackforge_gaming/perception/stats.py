from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class LatencySummary:
    count: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float


class RollingStats:
    """Statistiques glissantes de latence (fenêtre de ``window`` mesures)."""

    def __init__(self, window: int = 200) -> None:
        if window < 1:
            msg = "window doit être >= 1"
            raise ValueError(msg)
        self._values: deque[float] = deque(maxlen=window)

    def add(self, value_ms: float) -> None:
        self._values.append(value_ms)

    def summary(self) -> LatencySummary | None:
        if not self._values:
            return None
        data = np.fromiter(self._values, dtype=np.float64, count=len(self._values))
        return LatencySummary(
            count=len(data),
            mean_ms=float(data.mean()),
            p50_ms=float(np.percentile(data, 50)),
            p95_ms=float(np.percentile(data, 95)),
            max_ms=float(data.max()),
        )
