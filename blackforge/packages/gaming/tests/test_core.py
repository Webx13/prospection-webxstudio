from __future__ import annotations

import numpy as np
import pytest

from blackforge_gaming.core import (
    Detection,
    EmergencyStop,
    Frame,
    KillSwitch,
    NormRect,
    Rect,
)

# ----------------------------------------------------------------------------- Rect


def test_rect_rejects_empty_or_negative_size() -> None:
    for w, h in [(0, 5), (5, 0), (-1, 5), (5, -3)]:
        with pytest.raises(ValueError, match="strictement positive"):
            Rect(0, 0, w, h)


def test_rect_intersection_and_iou() -> None:
    a, b = Rect(0, 0, 10, 10), Rect(5, 5, 10, 10)
    assert a.intersection(b) == Rect(5, 5, 5, 5)
    assert a.iou(b) == pytest.approx(25 / 175)
    assert a.iou(a) == 1.0
    assert a.intersection(Rect(10, 0, 5, 5)) is None  # bords contigus : pas d'intersection
    assert a.iou(Rect(20, 20, 3, 3)) == 0.0


def test_rect_contains_translate_clamp() -> None:
    outer = Rect(0, 0, 100, 100)
    assert outer.contains(Rect(10, 10, 20, 20))
    assert outer.contains(outer)
    assert not outer.contains(Rect(90, 90, 20, 20))
    assert Rect(1, 2, 3, 4).translated(10, 20) == Rect(11, 22, 3, 4)
    assert Rect(-5, -5, 10, 10).clamped(100, 100) == Rect(0, 0, 5, 5)
    assert Rect(200, 200, 5, 5).clamped(100, 100) is None


def test_rect_from_xyxy_roundtrip() -> None:
    rect = Rect.from_xyxy(3, 4, 13, 24)
    assert (rect.x2, rect.y2, rect.area) == (13, 24, 200)


# ------------------------------------------------------------------------- NormRect


def test_normrect_validation() -> None:
    for args in [(-0.1, 0, 0.5, 0.5), (0, 0, 0, 0.5), (0.8, 0, 0.5, 0.5), (0, 0.9, 0.5, 0.5)]:
        with pytest.raises(ValueError, match="NormRect"):
            NormRect(*args)


def test_normrect_scales_with_resolution() -> None:
    area = NormRect(0.25, 0.5, 0.5, 0.25)
    assert area.to_rect(400, 200) == Rect(100, 100, 200, 50)
    assert area.to_rect(800, 400) == Rect(200, 200, 400, 100)  # même zone logique


def test_normrect_never_returns_an_empty_rect() -> None:
    tiny = NormRect(0.999, 0.999, 0.001, 0.001)
    rect = tiny.to_rect(10, 10)
    assert rect.w >= 1 and rect.h >= 1
    assert Rect(0, 0, 10, 10).contains(rect)


# -------------------------------------------------------------------------- Frame


def _image(h: int = 20, w: int = 30) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_frame_validates_image_shape_and_dtype() -> None:
    with pytest.raises(ValueError, match="uint8"):
        Frame(np.zeros((5, 5, 3), dtype=np.float32), 0, 0, "s")
    with pytest.raises(ValueError, match="HxWx3"):
        Frame(np.zeros((5, 5), dtype=np.uint8), 0, 0, "s")
    with pytest.raises(ValueError, match="HxWx3"):
        Frame(np.zeros((5, 5, 4), dtype=np.uint8), 0, 0, "s")
    with pytest.raises(ValueError, match="pixel_scale"):
        Frame(_image(), 0, 0, "s", pixel_scale=0)


def test_frame_image_is_read_only() -> None:
    frame = Frame(_image(), 0, 0, "s")
    with pytest.raises(ValueError, match="read-only"):
        frame.image[0, 0, 0] = 1


def test_frame_crop_is_a_view_and_checks_bounds() -> None:
    frame = Frame(_image(20, 30), 0, 0, "s")
    assert (frame.width, frame.height) == (30, 20)
    crop = frame.crop(Rect(5, 5, 10, 8))
    assert crop.shape == (8, 10, 3)
    assert np.shares_memory(crop, frame.image)
    assert frame.crop(Rect(25, 15, 20, 20)).shape == (5, 5, 3)  # recadrée
    with pytest.raises(ValueError, match="hors de l'image"):
        frame.crop(Rect(100, 100, 5, 5))


# ---------------------------------------------------------------------- Detection


def test_detection_validates_confidence_and_label() -> None:
    box = Rect(0, 0, 5, 5)
    with pytest.raises(ValueError, match="confidence"):
        Detection("x", 1.5, box, "d", "heuristic")
    with pytest.raises(ValueError, match="confidence"):
        Detection("x", -0.1, box, "d", "heuristic")
    with pytest.raises(ValueError, match="label"):
        Detection("", 0.5, box, "d", "heuristic")


def test_detection_translated_keeps_everything_else() -> None:
    det = Detection("enemy", 0.9, Rect(1, 2, 3, 4), "d", "similarity", attributes={"k": 1})
    moved = det.translated(10, 20)
    assert moved.box == Rect(11, 22, 3, 4)
    assert (moved.label, moved.confidence, moved.score_kind) == ("enemy", 0.9, "similarity")
    assert moved.attributes == {"k": 1}
    assert det.box == Rect(1, 2, 3, 4)  # l'original n'est pas modifié


# ---------------------------------------------------------------------- KillSwitch


def test_kill_switch_triggers_and_stays_until_reset() -> None:
    switch = KillSwitch()
    switch.raise_if_triggered()  # ne lève rien
    switch.trigger("bouton d'arrêt")
    switch.trigger("seconde raison ignorée")
    assert switch.is_triggered
    assert switch.reason == "bouton d'arrêt"
    with pytest.raises(EmergencyStop, match="bouton d'arrêt"):
        switch.raise_if_triggered()
    switch.reset()
    assert not switch.is_triggered
    assert switch.reason is None
    switch.raise_if_triggered()
