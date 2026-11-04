"""Adaptateur ONNX Runtime pour détecteurs de type YOLOv8/YOLO11 exportés en ONNX.

Ce paquet NE fournit AUCUN poids pré-entraîné et n'a PAS été évalué sur de vrais jeux : la qualité
de détection dépend entièrement du modèle fourni. Voir ``yolo_decode`` pour les formats gérés.

Sécurité : un fichier ``.onnx`` est un graphe de calcul analysé par ONNX Runtime ; ne chargez que
des modèles dont vous maîtrisez la provenance.

Licence : les outils et poids Ultralytics (YOLOv8/11) sont sous AGPL-3.0 ; ONNX Runtime (MIT) et
cet adaptateur n'en dépendent pas. Utiliser un modèle AGPL dans un service commercial a des
conséquences juridiques à valider avant tout déploiement.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from blackforge_gaming.core.capabilities import Availability, Capability
from blackforge_gaming.core.detection import Detection
from blackforge_gaming.core.types import Image
from blackforge_gaming.vision.yolo_decode import decode_yolov8, letterbox, to_model_input

# Ordre de préférence ; le CPU est toujours le dernier recours.
_PREFERRED_PROVIDERS = (
    "CUDAExecutionProvider",  # NVIDIA (Windows/Linux)
    "CoreMLExecutionProvider",  # Apple Silicon
    "DmlExecutionProvider",  # DirectML (Windows, GPU quelconque)
    "CPUExecutionProvider",
)


def select_providers(available: Sequence[str]) -> list[str]:
    """Choisit les backends d'exécution réellement disponibles, du plus au moins performant."""
    chosen = [p for p in _PREFERRED_PROVIDERS if p in available]
    if "CPUExecutionProvider" not in chosen:
        chosen.append("CPUExecutionProvider")
    return chosen


class OnnxDetector:
    def __init__(
        self,
        *,
        name: str,
        model_path: str | Path,
        labels: Sequence[str],
        input_size: tuple[int, int] | None = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        providers: Sequence[str] | None = None,
    ) -> None:
        import cv2
        import onnxruntime as ort

        if not labels:
            msg = "labels ne peut pas être vide"
            raise ValueError(msg)
        if not 0.0 < conf_threshold <= 1.0 or not 0.0 < iou_threshold <= 1.0:
            msg = "conf_threshold et iou_threshold doivent être dans ]0, 1]"
            raise ValueError(msg)
        self._cv2: Any = cv2
        self._name = name
        self._labels = tuple(labels)
        self._conf = conf_threshold
        self._iou = iou_threshold
        self.providers = (
            list(providers)
            if providers is not None
            else select_providers(ort.get_available_providers())
        )
        self._session = ort.InferenceSession(str(model_path), providers=self.providers)
        model_input = self._session.get_inputs()[0]
        self._input_name: str = model_input.name
        if input_size is None:
            shape = model_input.shape  # [1, 3, H, W] ; H/W valent None ou une chaîne si dynamiques
            if len(shape) != 4 or not all(isinstance(v, int) for v in shape[2:]):
                msg = "entrée du modèle dynamique : précisez input_size=(hauteur, largeur)"
                raise ValueError(msg)
            input_size = (int(shape[2]), int(shape[3]))
        self.input_size = input_size

    @property
    def name(self) -> str:
        return self._name

    @property
    def active_providers(self) -> list[str]:
        """Backends réellement retenus par ONNX Runtime pour cette session."""
        return list(self._session.get_providers())

    def detect(self, image: Image) -> Sequence[Detection]:
        height, width = image.shape[:2]
        boxed, scale, pad = letterbox(image, self.input_size, self._cv2)
        outputs = self._session.run(None, {self._input_name: to_model_input(boxed)})
        return decode_yolov8(
            outputs[0],
            labels=self._labels,
            detector_name=self._name,
            scale=scale,
            pad=pad,
            image_size_wh=(width, height),
            conf_threshold=self._conf,
            iou_threshold=self._iou,
        )


def probe_vision() -> list[Capability]:
    capabilities: list[Capability] = []
    try:
        import cv2

        capabilities.append(Capability("vision.opencv", Availability.AVAILABLE, cv2.__version__))
    except ImportError:
        capabilities.append(
            Capability("vision.opencv", Availability.UNAVAILABLE, "extra « vision » non installé")
        )
    try:
        import onnxruntime as ort

        available = ort.get_available_providers()
        capabilities.append(
            Capability("vision.onnxruntime", Availability.AVAILABLE, f"{ort.__version__}")
        )
        for provider in (
            "CUDAExecutionProvider",
            "CoreMLExecutionProvider",
            "DmlExecutionProvider",
        ):
            capabilities.append(
                Capability(
                    f"vision.accelerator.{provider.removesuffix('ExecutionProvider').lower()}",
                    Availability.AVAILABLE if provider in available else Availability.UNAVAILABLE,
                    "fourni par ONNX Runtime"
                    if provider in available
                    else "non fourni par cette installation",
                )
            )
    except ImportError:
        capabilities.append(
            Capability(
                "vision.onnxruntime", Availability.UNAVAILABLE, "extra « onnx » non installé"
            )
        )
    return capabilities
