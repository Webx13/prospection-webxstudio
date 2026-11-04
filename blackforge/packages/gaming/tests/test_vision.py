from __future__ import annotations

import cv2
import numpy as np
import pytest

from blackforge_gaming.core import Detector, Rect
from blackforge_gaming.vision import (
    ColorBlobDetector,
    TemplateDetector,
    non_max_suppression,
)
from tests.scenes import BLUE, GREEN, RED, blank, fill, paste, sprite

# ------------------------------------------------------------------------------- NMS


def test_nms_keeps_best_of_overlapping_boxes_and_all_separate_ones() -> None:
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=np.float64)
    scores = np.array([0.6, 0.9, 0.5])
    assert non_max_suppression(boxes, scores, 0.5) == [1, 2]


def test_nms_edge_cases() -> None:
    assert non_max_suppression(np.zeros((0, 4)), np.zeros(0), 0.5) == []
    one = np.array([[0, 0, 5, 5]], dtype=np.float64)
    assert non_max_suppression(one, np.array([0.1]), 0.5) == [0]
    degenerate = np.array(
        [[5, 5, 5, 5], [5, 5, 5, 5]], dtype=np.float64
    )  # aire nulle : pas de division par 0
    assert len(non_max_suppression(degenerate, np.array([0.5, 0.4]), 0.5)) == 2


# ------------------------------------------------------------------------- couleurs

RED_HSV = ((170, 120, 120), (10, 255, 255))  # teinte « qui fait le tour » : 170..179 et 0..10
GREEN_HSV = ((45, 120, 120), (75, 255, 255))


def red_detector(**kwargs: object) -> ColorBlobDetector:
    return ColorBlobDetector(
        name="red",
        label="enemy",
        hsv_lower=RED_HSV[0],
        hsv_upper=RED_HSV[1],
        **kwargs,  # type: ignore[arg-type]
    )


def test_color_detector_follows_the_protocol() -> None:
    assert isinstance(red_detector(), Detector)


def test_color_detector_finds_red_across_the_hue_wraparound() -> None:
    image = blank()
    truth = [Rect(20, 20, 30, 30), Rect(100, 60, 18, 40)]
    for rect in truth:
        fill(image, rect, RED)
    fill(
        image, Rect(200, 100, 25, 25), GREEN
    )  # un objet d'une autre couleur : ne doit pas apparaître
    found = red_detector().detect(image)
    assert [d.box for d in found] == truth
    assert all(d.confidence == 1.0 and d.score_kind == "heuristic" for d in found)
    assert all(d.label == "enemy" and d.detector == "red" for d in found)


def test_color_detector_distinguishes_colors() -> None:
    image = blank()
    fill(image, Rect(10, 10, 20, 20), GREEN)
    fill(image, Rect(60, 10, 20, 20), BLUE)
    green = ColorBlobDetector(
        name="g", label="ally", hsv_lower=GREEN_HSV[0], hsv_upper=GREEN_HSV[1]
    )
    assert [d.box for d in green.detect(image)] == [Rect(10, 10, 20, 20)]


def test_color_detector_filters_by_area_and_fill_ratio() -> None:
    image = blank()
    fill(image, Rect(10, 10, 3, 3), RED)  # trop petit (9 px)
    fill(image, Rect(40, 10, 30, 30), RED)  # bon
    # forme en L : boîte englobante 30x30 mais ~ 20 % remplie
    fill(image, Rect(100, 10, 30, 3), RED)
    fill(image, Rect(100, 10, 3, 30), RED)
    found = red_detector(min_area=16, min_fill_ratio=0.5).detect(image)
    assert [d.box for d in found] == [Rect(40, 10, 30, 30)]
    kept_l = red_detector(min_area=16, min_fill_ratio=0.1).detect(image)
    assert Rect(100, 10, 30, 30) in [d.box for d in kept_l]
    big_only = red_detector(min_area=16, max_area=500).detect(image)
    assert Rect(40, 10, 30, 30) not in [d.box for d in big_only]  # 900 px > 500


def test_color_detector_validates_parameters() -> None:
    with pytest.raises(ValueError, match="teinte"):
        ColorBlobDetector(name="x", label="x", hsv_lower=(200, 0, 0), hsv_upper=(10, 255, 255))
    with pytest.raises(ValueError, match="min_area"):
        red_detector(min_area=0)


def test_color_detector_returns_nothing_on_background() -> None:
    assert red_detector().detect(blank()) == []


# --------------------------------------------------------------------------- gabarit


def test_template_detector_finds_each_sprite_exactly_once() -> None:
    tpl = sprite()
    image = blank(400, 220)
    truth = [paste(image, tpl, 30, 20), paste(image, tpl, 200, 120), paste(image, tpl, 310, 40)]
    detector = TemplateDetector(name="hero", label="hero", template=tpl, threshold=0.9)
    found = detector.detect(image)
    assert sorted((d.box.x, d.box.y) for d in found) == sorted((r.x, r.y) for r in truth)
    assert all(d.box.w == tpl.shape[1] and d.box.h == tpl.shape[0] for d in found)
    assert all(d.score_kind == "similarity" and d.confidence > 0.99 for d in found)


def test_template_detector_returns_nothing_when_absent() -> None:
    detector = TemplateDetector(name="hero", label="hero", template=sprite(), threshold=0.9)
    image = blank(300, 200)
    fill(image, Rect(40, 40, 24, 24), RED)  # un carré uni ne ressemble pas au sprite
    assert detector.detect(image) == []


def test_template_detector_is_multiscale() -> None:
    tpl = sprite(cell_px=2)  # 24x24
    scaled = cv2.resize(tpl, (36, 36), interpolation=cv2.INTER_NEAREST)  # x1,5
    image = blank(300, 200)
    paste(image, np.asarray(scaled, dtype=np.uint8), 100, 80)
    single = TemplateDetector(name="s", label="hero", template=tpl, threshold=0.8)
    multi = TemplateDetector(
        name="m", label="hero", template=tpl, threshold=0.8, scales=(1.0, 1.25, 1.5, 1.75)
    )
    assert single.detect(image) == []
    best = max(multi.detect(image), key=lambda d: d.confidence)
    assert abs(best.box.x - 100) <= 2 and abs(best.box.y - 80) <= 2
    assert abs(best.box.w - 36) <= 2


def test_template_detector_edge_cases() -> None:
    tpl = sprite()
    detector = TemplateDetector(name="hero", label="hero", template=tpl, threshold=0.9)
    assert detector.detect(blank(10, 10)) == []  # image plus petite que le gabarit
    with pytest.raises(ValueError, match="uniforme"):
        TemplateDetector(name="x", label="x", template=blank(10, 10))
    with pytest.raises(ValueError, match="BGR"):
        TemplateDetector(name="x", label="x", template=np.zeros((5, 5), np.uint8))
    with pytest.raises(ValueError, match="threshold"):
        TemplateDetector(name="x", label="x", template=tpl, threshold=0)
    with pytest.raises(ValueError, match="scales"):
        TemplateDetector(name="x", label="x", template=tpl, scales=())


def test_template_detector_accepts_readonly_and_noncontiguous_input() -> None:
    tpl = sprite()
    image = blank(300, 200)
    paste(image, tpl, 50, 50)
    image.setflags(write=False)
    detector = TemplateDetector(name="hero", label="hero", template=tpl, threshold=0.9)
    assert len(detector.detect(image)) == 1
    window = image[20:150, 10:200]  # vue non contiguë, comme un recadrage de région d'intérêt
    assert len(detector.detect(window)) == 1


def test_color_detector_has_no_notion_of_shape_or_context() -> None:
    """LIMITE DOCUMENTÉE : une cellule rouge d'un sprite est « rouge » comme un ennemi rouge.

    Le détecteur par couleur ne connaît ni la forme ni le contexte : filtrer par taille
    (``min_area``), restreindre à une région d'intérêt, ou utiliser un détecteur par gabarit/modèle.
    """
    image = blank()
    paste(image, sprite(), 50, 50)
    assert len(red_detector(min_area=1).detect(image)) > 0
    assert red_detector(min_area=400).detect(image) == []
