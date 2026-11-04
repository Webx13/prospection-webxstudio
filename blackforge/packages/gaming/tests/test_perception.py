from __future__ import annotations

import numpy as np
import pytest

from blackforge_gaming.core import Detection, Frame, NormRect, Rect
from blackforge_gaming.core.types import Image
from blackforge_gaming.perception import (
    ChangeDetector,
    DetectorBinding,
    PerceptionPipeline,
    RegionOfInterest,
    RollingStats,
)
from blackforge_gaming.vision import ColorBlobDetector
from tests.scenes import GREEN, RED, blank, fill

RED_DETECTOR = ColorBlobDetector(
    name="red", label="enemy", hsv_lower=(170, 120, 120), hsv_upper=(10, 255, 255)
)


def frame_of(image: Image, index: int = 0) -> Frame:
    return Frame(image, index=index, captured_at_ns=index * 33_000_000, source_id="test")


class StubDetector:
    """Détecteur configurable pour tester l'orchestration (pas la vision)."""

    def __init__(self, name: str, result: list[Detection] | Exception) -> None:
        self._name = name
        self._result = result
        self.calls: list[tuple[int, int]] = []

    @property
    def name(self) -> str:
        return self._name

    def detect(self, image: Image) -> list[Detection]:
        self.calls.append((image.shape[1], image.shape[0]))
        if isinstance(self._result, Exception):
            raise self._result
        return list(self._result)


# ------------------------------------------------------------------------ pipeline


def test_pipeline_detects_and_reports_timings() -> None:
    image = blank()
    fill(image, Rect(20, 20, 30, 30), RED)
    pipeline = PerceptionPipeline([DetectorBinding(RED_DETECTOR)])
    result = pipeline.process(frame_of(image, index=7))
    assert result.analyzed and not result.degraded
    assert [d.box for d in result.detections] == [Rect(20, 20, 30, 30)]
    assert (result.frame_index, result.frame_size) == (7, (320, 180))
    assert [t.name for t in result.timings] == ["red"]
    assert result.total_ms >= result.timings[0].ms >= 0
    summary = pipeline.latency_summary()
    assert summary is not None and summary.count == 1


def test_roi_detections_are_translated_back_to_frame_coordinates() -> None:
    image = blank(400, 200)
    fill(image, Rect(300, 20, 30, 30), RED)  # dans la zone
    fill(image, Rect(20, 20, 30, 30), RED)  # hors zone : ne doit pas être vu
    roi = RegionOfInterest("right_half", NormRect(0.5, 0.0, 0.5, 1.0))
    pipeline = PerceptionPipeline([DetectorBinding(RED_DETECTOR, roi="right_half")], rois=[roi])
    result = pipeline.process(frame_of(image))
    assert [d.box for d in result.detections] == [Rect(300, 20, 30, 30)]


def test_same_normalized_roi_works_at_different_resolutions() -> None:
    roi = RegionOfInterest("zone", NormRect(0.5, 0.5, 0.5, 0.5))
    results = []
    for factor in (1, 2, 3):
        image = blank(200 * factor, 100 * factor)
        fill(image, Rect(150 * factor, 60 * factor, 20 * factor, 20 * factor), RED)
        fill(image, Rect(10 * factor, 10 * factor, 20 * factor, 20 * factor), RED)  # hors zone
        pipeline = PerceptionPipeline([DetectorBinding(RED_DETECTOR, "zone")], rois=[roi])
        results.append(pipeline.process(frame_of(image)))
    for factor, result in zip((1, 2, 3), results, strict=True):
        assert [d.box for d in result.detections] == [
            Rect(150 * factor, 60 * factor, 20 * factor, 20 * factor)
        ]


def test_a_failing_detector_is_isolated_and_reported() -> None:
    good = StubDetector("good", [Detection("x", 0.9, Rect(1, 1, 5, 5), "good", "heuristic")])
    bad = StubDetector("bad", RuntimeError("modèle corrompu"))
    pipeline = PerceptionPipeline([DetectorBinding(bad), DetectorBinding(good)])
    result = pipeline.process(frame_of(blank()))
    assert len(result.detections) == 1  # le bon détecteur a quand même travaillé
    assert result.degraded
    assert result.errors[0].detector == "bad"
    assert "modèle corrompu" in result.errors[0].message
    assert {t.name for t in result.timings} == {"bad", "good"}


def test_pipeline_validates_its_configuration() -> None:
    a, b = StubDetector("same", []), StubDetector("same", [])
    with pytest.raises(ValueError, match="en double"):
        PerceptionPipeline([DetectorBinding(a), DetectorBinding(b)])
    with pytest.raises(ValueError, match="inconnues"):
        PerceptionPipeline([DetectorBinding(a, roi="nope")])
    roi = RegionOfInterest("r", NormRect(0, 0, 1, 1))
    with pytest.raises(ValueError, match="en double"):
        PerceptionPipeline([DetectorBinding(a)], rois=[roi, roi])


# --------------------------------------------------------------- analyse événementielle


def scene_with_square(x: int) -> Image:
    image = blank()
    fill(image, Rect(x, 40, 40, 40), RED)
    return image


def test_unchanged_frames_are_skipped_and_reuse_previous_detections() -> None:
    detector = StubDetector("d", [Detection("x", 0.9, Rect(1, 1, 5, 5), "d", "heuristic")])
    pipeline = PerceptionPipeline([DetectorBinding(detector)], change_detector=ChangeDetector())
    results = [pipeline.process(frame_of(scene_with_square(50), i)) for i in range(4)]
    assert [r.analyzed for r in results] == [True, False, False, False]
    assert len(detector.calls) == 1  # le détecteur n'a tourné qu'une fois
    assert all(r.detections == results[0].detections for r in results)
    assert results[1].change_score is not None and results[1].change_score < 0.01


def test_a_visible_change_triggers_a_new_analysis() -> None:
    pipeline = PerceptionPipeline(
        [DetectorBinding(RED_DETECTOR)], change_detector=ChangeDetector(threshold=0.005)
    )
    first = pipeline.process(frame_of(scene_with_square(50), 0))
    same = pipeline.process(frame_of(scene_with_square(50), 1))
    moved = pipeline.process(frame_of(scene_with_square(200), 2))
    assert (first.analyzed, same.analyzed, moved.analyzed) == (True, False, True)
    assert moved.detections[0].box == Rect(200, 40, 40, 40)
    assert moved.change_score is not None and moved.change_score > 0.005


def test_staleness_is_bounded() -> None:
    """Même sans changement, une analyse est forcée toutes les ``max_stale_frames`` images."""
    detector = StubDetector("d", [])
    pipeline = PerceptionPipeline(
        [DetectorBinding(detector)], change_detector=ChangeDetector(), max_stale_frames=3
    )
    analyzed = [pipeline.process(frame_of(blank(), i)).analyzed for i in range(9)]
    assert analyzed == [True, False, False, False, True, False, False, False, True]


def test_slow_drift_eventually_triggers_analysis() -> None:
    """La référence n'avance que sur images analysées : une dérive lente n'est pas ignorée."""
    detector = StubDetector("d", [])
    pipeline = PerceptionPipeline(
        [DetectorBinding(detector)],
        change_detector=ChangeDetector(threshold=0.02),
        max_stale_frames=10_000,
    )
    flags = []
    for i in range(40):
        image = blank()
        image[:, :] = (16 + i * 2, 16, 16)  # éclaircissement très progressif
        flags.append(pipeline.process(frame_of(image, i)).analyzed)
    assert flags[0] is True
    assert any(flags[1:])  # un changement cumulé finit par être détecté


def test_resolution_change_forces_analysis() -> None:
    pipeline = PerceptionPipeline(
        [DetectorBinding(StubDetector("d", []))], change_detector=ChangeDetector()
    )
    assert pipeline.process(frame_of(blank(320, 180), 0)).analyzed
    assert pipeline.process(frame_of(blank(640, 360), 1)).analyzed


def test_change_detector_score_range_and_validation() -> None:
    detector = ChangeDetector()
    assert detector.score(blank()) == 1.0  # pas de référence
    detector.accept(blank())
    assert detector.score(blank()) == 0.0
    white = np.full((180, 320, 3), 255, dtype=np.uint8)
    black = np.zeros((180, 320, 3), dtype=np.uint8)
    detector.accept(black)
    assert detector.score(white) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="threshold"):
        ChangeDetector(threshold=0)


def test_change_detector_ignores_sensor_noise_level_differences() -> None:
    detector = ChangeDetector(threshold=0.01)
    base = blank()
    detector.accept(base)
    noisy = base.copy()
    noisy[::7, ::5] = np.clip(noisy[::7, ::5].astype(int) + 3, 0, 255).astype(np.uint8)
    assert detector.score(noisy) < 0.01


# ------------------------------------------------------------------------------- stats


def test_rolling_stats_summary() -> None:
    stats = RollingStats(window=5)
    assert stats.summary() is None
    for value in [10, 20, 30, 40, 50, 1000]:  # 1000 évince 10 (fenêtre de 5)
        stats.add(value)
    summary = stats.summary()
    assert summary is not None
    assert summary.count == 5 and summary.max_ms == 1000
    assert summary.p50_ms == 40
    with pytest.raises(ValueError, match="window"):
        RollingStats(window=0)


def test_unrelated_colors_do_not_leak_between_detectors() -> None:
    image = blank()
    fill(image, Rect(10, 10, 20, 20), RED)
    fill(image, Rect(60, 10, 20, 20), GREEN)
    green = ColorBlobDetector(
        name="green", label="ally", hsv_lower=(45, 120, 120), hsv_upper=(75, 255, 255)
    )
    pipeline = PerceptionPipeline([DetectorBinding(RED_DETECTOR), DetectorBinding(green)])
    result = pipeline.process(frame_of(image))
    by_label = {d.label: d.box for d in result.detections}
    assert by_label == {"enemy": Rect(10, 10, 20, 20), "ally": Rect(60, 10, 20, 20)}
