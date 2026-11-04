"""Profil de vision déclaratif d'un jeu : quoi détecter, où, avec quels réglages.

Pure donnée : aucun code de plugin n'est exécuté. Le profil est transformé en moteurs par la
racine de composition (``blackforge_gaming.assemble``).
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_NAME = r"^[a-z][a-z0-9_]{0,39}$"
_LABEL = r"^[a-zA-Z][a-zA-Z0-9_ -]{0,39}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RegionSpec(_Strict):
    """Région d'intérêt en coordonnées normalisées (0..1) : valable à toute résolution."""

    name: str = Field(pattern=_NAME)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _inside_image(self) -> Self:
        if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
            msg = f"la région {self.name!r} dépasse de l'image"
            raise ValueError(msg)
        return self


class _DetectorBase(_Strict):
    name: str = Field(pattern=_NAME)
    label: str = Field(pattern=_LABEL)
    roi: str | None = Field(default=None, pattern=_NAME)


class ColorDetectorSpec(_DetectorBase):
    kind: Literal["color"]
    hsv_lower: tuple[int, int, int]
    hsv_upper: tuple[int, int, int]
    min_area: int = Field(default=16, ge=1)
    max_area: int | None = Field(default=None, ge=1)
    min_fill_ratio: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _hsv_ranges(self) -> Self:
        for triple in (self.hsv_lower, self.hsv_upper):
            h, s, v = triple
            if not (0 <= h <= 179 and 0 <= s <= 255 and 0 <= v <= 255):
                msg = "HSV hors bornes (H 0-179, S et V 0-255)"
                raise ValueError(msg)
        return self


class TemplateDetectorSpec(_DetectorBase):
    kind: Literal["template"]
    template: str = Field(min_length=1, max_length=200)  # chemin relatif au dossier du plugin
    threshold: float = Field(default=0.85, gt=0.0, le=1.0)
    scales: tuple[float, ...] = Field(default=(1.0,), min_length=1, max_length=8)

    @model_validator(mode="after")
    def _scales_positive(self) -> Self:
        if any(s <= 0 or s > 8 for s in self.scales):
            msg = "scales doit contenir des valeurs dans ]0, 8]"
            raise ValueError(msg)
        return self


class OnnxDetectorSpec(_DetectorBase):
    kind: Literal["onnx"]
    model: str = Field(min_length=1, max_length=200)  # chemin relatif au dossier du plugin
    labels: tuple[str, ...] = Field(min_length=1, max_length=200)
    input_size: tuple[int, int] | None = None
    conf_threshold: float = Field(default=0.25, gt=0.0, le=1.0)
    iou_threshold: float = Field(default=0.45, gt=0.0, le=1.0)


DetectorSpec = Annotated[
    ColorDetectorSpec | TemplateDetectorSpec | OnnxDetectorSpec, Field(discriminator="kind")
]


class VisionProfile(_Strict):
    regions: tuple[RegionSpec, ...] = ()
    detectors: tuple[DetectorSpec, ...] = Field(default=(), max_length=64)
    change_threshold: float | None = Field(
        default=0.002, gt=0.0, le=1.0
    )  # None = analyser chaque image
    max_stale_frames: int = Field(default=30, ge=0, le=10_000)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        region_names = [r.name for r in self.regions]
        if len(set(region_names)) != len(region_names):
            msg = "noms de régions en double"
            raise ValueError(msg)
        detector_names = [d.name for d in self.detectors]
        if len(set(detector_names)) != len(detector_names):
            msg = "noms de détecteurs en double"
            raise ValueError(msg)
        unknown = {d.roi for d in self.detectors if d.roi is not None} - set(region_names)
        if unknown:
            msg = f"régions inconnues : {sorted(unknown)}"
            raise ValueError(msg)
        return self

    def referenced_files(self) -> tuple[str, ...]:
        """Chemins relatifs de tous les fichiers (gabarits, modèles) que le profil exige."""
        paths: list[str] = []
        for detector in self.detectors:
            if isinstance(detector, TemplateDetectorSpec):
                paths.append(detector.template)
            elif isinstance(detector, OnnxDetectorSpec):
                paths.append(detector.model)
        return tuple(paths)
