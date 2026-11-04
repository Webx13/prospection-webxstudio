"""Pipeline de perception : image → détections structurées, avec mesures et isolation des pannes.

Indépendant de tout moteur concret : il ne connaît que les protocoles ``Detector`` et la
structure ``Frame``. Les détecteurs sont injectés.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from blackforge_gaming.core.detection import Detection
from blackforge_gaming.core.frame import Frame
from blackforge_gaming.core.geometry import NormRect
from blackforge_gaming.core.protocols import Detector
from blackforge_gaming.perception.change import ChangeDetector
from blackforge_gaming.perception.stats import LatencySummary, RollingStats

logger = logging.getLogger("blackforge.gaming.perception")


@dataclass(frozen=True, slots=True)
class RegionOfInterest:
    """Zone nommée en coordonnées normalisées : identique à toute résolution."""

    name: str
    area: NormRect


@dataclass(frozen=True, slots=True)
class DetectorBinding:
    """Associe un détecteur à une zone (``roi=None`` = image entière)."""

    detector: Detector
    roi: str | None = None


@dataclass(frozen=True, slots=True)
class StageTiming:
    name: str
    ms: float


@dataclass(frozen=True, slots=True)
class DetectorError:
    detector: str
    message: str


@dataclass(frozen=True, slots=True)
class Perception:
    """État perçu pour une image. C'est l'entrée du futur Game State Manager."""

    frame_index: int
    captured_at_ns: int
    frame_size: tuple[int, int]  # (largeur, hauteur)
    analyzed: bool  # False : image jugée inchangée, détections reprises de l'analyse précédente
    change_score: float | None
    detections: tuple[Detection, ...]  # en coordonnées de l'image entière
    timings: tuple[StageTiming, ...]
    total_ms: float
    errors: tuple[DetectorError, ...] = ()

    @property
    def degraded(self) -> bool:
        """Vrai si au moins un détecteur a échoué : les détections peuvent être incomplètes."""
        return bool(self.errors)


class PerceptionPipeline:
    def __init__(
        self,
        bindings: Sequence[DetectorBinding],
        *,
        rois: Sequence[RegionOfInterest] = (),
        change_detector: ChangeDetector | None = None,
        max_stale_frames: int = 30,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        names = [b.detector.name for b in bindings]
        if len(set(names)) != len(names):
            msg = f"noms de détecteurs en double : {sorted(n for n in names if names.count(n) > 1)}"
            raise ValueError(msg)
        self._rois = {r.name: r for r in rois}
        if len(self._rois) != len(rois):
            msg = "noms de régions d'intérêt en double"
            raise ValueError(msg)
        unknown = {b.roi for b in bindings if b.roi is not None} - self._rois.keys()
        if unknown:
            msg = f"régions d'intérêt inconnues : {sorted(unknown)}"
            raise ValueError(msg)
        if max_stale_frames < 0:
            msg = "max_stale_frames doit être >= 0"
            raise ValueError(msg)
        self._bindings = tuple(bindings)
        self._change = change_detector
        self._max_stale = max_stale_frames
        self._clock = clock_ns
        self._last: Perception | None = None
        self._skipped_in_a_row = 0
        self.latency = RollingStats()

    def latency_summary(self) -> LatencySummary | None:
        return self.latency.summary()

    def process(self, frame: Frame) -> Perception:
        started = self._clock()
        change_score: float | None = None
        if self._change is not None:
            change_score = self._change.score(frame.image)
            unchanged = change_score < self._change.threshold
            # Des boîtes en pixels n'ont de sens que pour la résolution qui les a produites.
            same_size = self._last is not None and self._last.frame_size == (
                frame.width,
                frame.height,
            )
            if unchanged and same_size and self._skipped_in_a_row < self._max_stale:
                self._skipped_in_a_row += 1
                return self._finish(
                    Perception(
                        frame_index=frame.index,
                        captured_at_ns=frame.captured_at_ns,
                        frame_size=(frame.width, frame.height),
                        analyzed=False,
                        change_score=change_score,
                        detections=self._last.detections if self._last else (),
                        timings=(StageTiming("change", self._ms_since(started)),),
                        total_ms=0.0,
                        errors=self._last.errors if self._last else (),
                    ),
                    started,
                )
        self._skipped_in_a_row = 0
        timings: list[StageTiming] = []
        if self._change is not None:
            timings.append(StageTiming("change", self._ms_since(started)))
        detections: list[Detection] = []
        errors: list[DetectorError] = []
        for binding in self._bindings:
            t0 = self._clock()
            try:
                detections.extend(self._run(binding, frame))
            except Exception as exc:  # un détecteur défaillant ne doit pas faire tomber l'agent
                logger.exception("detector_failed", extra={"detector": binding.detector.name})
                errors.append(DetectorError(binding.detector.name, f"{type(exc).__name__}: {exc}"))
            timings.append(StageTiming(binding.detector.name, self._ms_since(t0)))
        if self._change is not None:
            self._change.accept(frame.image)
        return self._finish(
            Perception(
                frame_index=frame.index,
                captured_at_ns=frame.captured_at_ns,
                frame_size=(frame.width, frame.height),
                analyzed=True,
                change_score=change_score,
                detections=tuple(detections),
                timings=tuple(timings),
                total_ms=0.0,
                errors=tuple(errors),
            ),
            started,
        )

    # ------------------------------------------------------------------ internes

    def _run(self, binding: DetectorBinding, frame: Frame) -> list[Detection]:
        if binding.roi is None:
            return list(binding.detector.detect(frame.image))
        rect = self._rois[binding.roi].area.to_rect(frame.width, frame.height)
        crop = frame.crop(rect)
        return [d.translated(rect.x, rect.y) for d in binding.detector.detect(crop)]

    def _ms_since(self, start_ns: int) -> float:
        return (self._clock() - start_ns) / 1e6

    def _finish(self, result: Perception, started_ns: int) -> Perception:
        total = self._ms_since(started_ns)
        finished = Perception(
            frame_index=result.frame_index,
            captured_at_ns=result.captured_at_ns,
            frame_size=result.frame_size,
            analyzed=result.analyzed,
            change_score=result.change_score,
            detections=result.detections,
            timings=result.timings,
            total_ms=total,
            errors=result.errors,
        )
        self.latency.add(total)
        self._last = finished if finished.analyzed else self._last
        return finished
