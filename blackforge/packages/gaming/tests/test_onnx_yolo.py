"""Adaptateur ONNX/YOLO.

IMPORTANT : le modèle ONNX utilisé ici est fabriqué dans le test et renvoie une sortie CONSTANTE.
Cela vérifie la plomberie (chargement ONNX Runtime, letterbox, retour au repère de l'image,
décodage, NMS, validation de format) — PAS la qualité de détection d'un vrai modèle YOLO.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from blackforge_gaming.core import Detector
from blackforge_gaming.vision import (
    OnnxDetector,
    decode_yolov8,
    letterbox,
    select_providers,
    to_model_input,
)
from tests.onnx_helpers import COLUMNS, LABELS
from tests.onnx_helpers import make_constant_yolo_model as make_model
from tests.scenes import blank

# ---------------------------------------------------------------------------- letterbox


def test_letterbox_preserves_aspect_ratio_and_reports_padding() -> None:
    image = blank(128, 64)  # 2:1
    boxed, scale, (pad_x, pad_y) = letterbox(image, (64, 64), cv2)
    assert boxed.shape == (64, 64, 3)
    assert scale == 0.5
    assert (pad_x, pad_y) == (0, 16)  # bandes grises en haut et en bas
    assert tuple(boxed[0, 0]) == (114, 114, 114)
    assert tuple(boxed[32, 32]) == tuple(image[0, 0])


def test_model_input_is_rgb_nchw_float() -> None:
    bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    bgr[:, :] = (10, 20, 30)  # B, G, R
    blob = to_model_input(bgr)
    assert blob.shape == (1, 3, 4, 4) and blob.dtype == np.float32
    assert blob[0, 0, 0, 0] == pytest.approx(30 / 255)  # canal 0 = R
    assert blob[0, 2, 0, 0] == pytest.approx(10 / 255)  # canal 2 = B


# ------------------------------------------------------------------------------ décodage


def decode(columns: np.ndarray = COLUMNS, **kwargs: object):  # type: ignore[no-untyped-def]
    params: dict[str, object] = {
        "labels": LABELS,
        "detector_name": "yolo",
        "scale": 0.5,
        "pad": (0, 16),
        "image_size_wh": (128, 64),
        "conf_threshold": 0.25,
        "iou_threshold": 0.45,
    }
    params.update(kwargs)
    return decode_yolov8(columns[np.newaxis], **params)  # type: ignore[arg-type]


def test_decode_maps_boxes_back_to_original_image_coordinates() -> None:
    enemy = max((d for d in decode() if d.label == "enemy"), key=lambda d: d.confidence)
    # A : (cx=32,cy=32,w=16,h=16) dans le modèle → coin (24,24) ; retour à l'image :
    # x = (24 - pad_x) / 0.5 = 48 ; y = (24 - pad_y) / 0.5 = (24 - 16) / 0.5 = 16 ; taille 16 / 0.5 = 32.
    assert (enemy.box.x, enemy.box.y, enemy.box.w, enemy.box.h) == (48, 16, 32, 32)
    assert enemy.confidence == pytest.approx(0.9)
    assert enemy.score_kind == "model_score"


def test_decode_applies_threshold_and_nms_per_class() -> None:
    found = decode()
    labels = sorted(d.label for d in found)
    # A' est un doublon de A (même classe) : supprimé. C est sous le seuil. D (classe 1) recouvre A
    # mais appartient à une autre classe : conservé. B (classe 0, ailleurs) : conservé.
    assert labels == ["ally", "enemy", "enemy"]
    assert sorted(d.confidence for d in found if d.label == "enemy") == pytest.approx([0.7, 0.9])


def test_decode_clips_to_image_and_drops_degenerate_boxes() -> None:
    columns = np.array(
        [[2.0, 200.0], [30.0, 30.0], [40.0, 10.0], [40.0, 10.0], [0.9, 0.9], [0.0, 0.0]],
        dtype=np.float32,
    )
    found = decode(columns, scale=1.0, pad=(0, 0), image_size_wh=(100, 60))
    assert len(found) == 1  # la 2e boîte est entièrement hors image après recadrage
    box = found[0].box
    assert box.x == 0  # recadrée : cx=2, w=40 → x1=-18 → 0
    assert box.x2 <= 100 and box.y2 <= 60


def test_decode_rejects_unknown_output_formats_instead_of_guessing() -> None:
    with pytest.raises(ValueError, match="attendu"):
        decode_yolov8(
            np.zeros((5, 6), np.float32),
            labels=LABELS,
            detector_name="y",
            scale=1,
            pad=(0, 0),
            image_size_wh=(10, 10),
            conf_threshold=0.1,
            iou_threshold=0.5,
        )
    with pytest.raises(ValueError, match="4 \\+ nc"):
        decode(labels=("only_one",))  # le modèle a 2 classes, on en déclare 1


def test_decode_returns_nothing_below_threshold() -> None:
    assert decode(conf_threshold=0.99) == []


# ------------------------------------------------------------------------ ONNX Runtime


def test_select_providers_prefers_accelerators_and_always_ends_with_cpu() -> None:
    assert select_providers(["CPUExecutionProvider"]) == ["CPUExecutionProvider"]
    assert select_providers(["CoreMLExecutionProvider", "CPUExecutionProvider"]) == [
        "CoreMLExecutionProvider",
        "CPUExecutionProvider",
    ]
    assert select_providers(
        ["CPUExecutionProvider", "CUDAExecutionProvider", "CoreMLExecutionProvider"]
    ) == ["CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]
    assert select_providers([]) == ["CPUExecutionProvider"]  # le CPU est toujours ajouté
    assert "TensorrtExecutionProvider" not in select_providers(["TensorrtExecutionProvider"])


def test_onnx_detector_runs_a_real_onnxruntime_session(tmp_path: Path) -> None:
    detector = OnnxDetector(name="yolo", model_path=make_model(tmp_path / "m.onnx"), labels=LABELS)
    assert isinstance(detector, Detector)
    assert detector.input_size == (64, 64)  # lu depuis le modèle
    assert "CPUExecutionProvider" in detector.active_providers
    found = detector.detect(blank(128, 64))  # letterbox : échelle 0.5, bandes en haut/bas
    assert sorted(d.label for d in found) == ["ally", "enemy", "enemy"]
    top = max(found, key=lambda d: d.confidence)
    assert (top.box.x, top.box.y, top.box.w, top.box.h) == (48, 16, 32, 32)


def test_onnx_detector_requires_input_size_when_model_is_dynamic(tmp_path: Path) -> None:
    path = make_model(tmp_path / "dyn.onnx", input_shape=["N", 3, "H", "W"])
    with pytest.raises(ValueError, match="input_size"):
        OnnxDetector(name="y", model_path=path, labels=LABELS)
    ok = OnnxDetector(name="y", model_path=path, labels=LABELS, input_size=(64, 64))
    assert len(ok.detect(blank(64, 64))) >= 1


def test_onnx_detector_rejects_a_label_count_that_does_not_match_the_model(tmp_path: Path) -> None:
    detector = OnnxDetector(
        name="y", model_path=make_model(tmp_path / "m.onnx"), labels=("a", "b", "c")
    )
    with pytest.raises(ValueError, match="4 \\+ nc"):
        detector.detect(blank(64, 64))


def test_onnx_detector_validates_arguments(tmp_path: Path) -> None:
    path = make_model(tmp_path / "m.onnx")
    with pytest.raises(ValueError, match="labels"):
        OnnxDetector(name="y", model_path=path, labels=())
    with pytest.raises(ValueError, match="conf_threshold"):
        OnnxDetector(name="y", model_path=path, labels=LABELS, conf_threshold=0)


def test_portrait_images_are_padded_horizontally_and_mapped_back_correctly(tmp_path: Path) -> None:
    """Image 64x128 (portrait) → entrée 64x64 : échelle 0.5 et marges à GAUCHE/DROITE (pad_x=16).

    Complète les cas paysage (marges haut/bas) : un oubli de pad_x au décodage passerait sinon inaperçu.
    """
    image = blank(64, 128)
    _, scale, pad = letterbox(image, (64, 64), cv2)
    assert (scale, pad) == (0.5, (16, 0))
    # A : coin modèle (24, 24) → x = (24 - 16) / 0.5 = 16 ; y = (24 - 0) / 0.5 = 48 ; taille 32.
    found = decode(scale=scale, pad=pad, image_size_wh=(64, 128))
    enemy = max((d for d in found if d.label == "enemy"), key=lambda d: d.confidence)
    assert (enemy.box.x, enemy.box.y, enemy.box.w, enemy.box.h) == (16, 48, 32, 32)
    # Et de bout en bout, à travers ONNX Runtime.
    detector = OnnxDetector(name="y", model_path=make_model(tmp_path / "m.onnx"), labels=LABELS)
    top = max(detector.detect(image), key=lambda d: d.confidence)
    assert (top.box.x, top.box.y, top.box.w, top.box.h) == (16, 48, 32, 32)
