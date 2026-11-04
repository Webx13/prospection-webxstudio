"""Racine de composition : transforme un plugin VALIDÉ en pipeline de perception.

Seul endroit qui connaît à la fois le SDK de plugins, la vision et la perception. Les chemins de
gabarits et de modèles passent par ``LoadedPlugin.resolve`` : déjà confinés et vérifiés (SHA-256)
au chargement du plugin.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blackforge_gaming.core.geometry import NormRect
from blackforge_gaming.core.protocols import Detector
from blackforge_gaming.perception import (
    ChangeDetector,
    DetectorBinding,
    PerceptionPipeline,
    RegionOfInterest,
)
from blackforge_gaming.plugin import (
    ColorDetectorSpec,
    LoadedPlugin,
    OnnxDetectorSpec,
    TemplateDetectorSpec,
)
from blackforge_gaming.vision import ColorBlobDetector, OnnxDetector, TemplateDetector


def _load_template(plugin: LoadedPlugin, relative: str) -> Any:
    import cv2

    data = np.fromfile(plugin.resolve(relative), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        msg = f"gabarit illisible ou format d'image non supporté : {relative!r}"
        raise ValueError(msg)
    return image


def build_pipeline(plugin: LoadedPlugin) -> PerceptionPipeline:
    """Construit le pipeline décrit par ``plugin.manifest.vision``."""
    profile = plugin.manifest.vision
    bindings: list[DetectorBinding] = []
    for spec in profile.detectors:
        detector: Detector
        if isinstance(spec, ColorDetectorSpec):
            detector = ColorBlobDetector(
                name=spec.name,
                label=spec.label,
                hsv_lower=spec.hsv_lower,
                hsv_upper=spec.hsv_upper,
                min_area=spec.min_area,
                max_area=spec.max_area,
                min_fill_ratio=spec.min_fill_ratio,
            )
        elif isinstance(spec, TemplateDetectorSpec):
            detector = TemplateDetector(
                name=spec.name,
                label=spec.label,
                template=_load_template(plugin, spec.template),
                threshold=spec.threshold,
                scales=spec.scales,
            )
        elif isinstance(spec, OnnxDetectorSpec):
            detector = OnnxDetector(
                name=spec.name,
                model_path=plugin.resolve(spec.model),
                labels=spec.labels,
                input_size=spec.input_size,
                conf_threshold=spec.conf_threshold,
                iou_threshold=spec.iou_threshold,
            )
        else:  # pragma: no cover - l'union discriminée est exhaustive
            msg = f"type de détecteur inconnu : {spec!r}"
            raise TypeError(msg)
        bindings.append(DetectorBinding(detector, spec.roi))
    return PerceptionPipeline(
        bindings,
        rois=[RegionOfInterest(r.name, NormRect(r.x, r.y, r.w, r.h)) for r in profile.regions],
        change_detector=(
            ChangeDetector(profile.change_threshold)
            if profile.change_threshold is not None
            else None
        ),
        max_stale_frames=profile.max_stale_frames,
    )
