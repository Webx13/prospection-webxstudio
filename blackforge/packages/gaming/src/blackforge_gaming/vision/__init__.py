"""Vision Engine : détecteurs interchangeables respectant le protocole ``Detector``.

Les détecteurs importent leurs dépendances lourdes (OpenCV, ONNX Runtime) à la construction,
pas à l'import du paquet : on peut importer ``blackforge_gaming.vision`` sans elles.
"""

from blackforge_gaming.vision.color import ColorBlobDetector
from blackforge_gaming.vision.nms import non_max_suppression
from blackforge_gaming.vision.onnx import OnnxDetector, probe_vision, select_providers
from blackforge_gaming.vision.template import TemplateDetector
from blackforge_gaming.vision.yolo_decode import decode_yolov8, letterbox, to_model_input

__all__ = [
    "ColorBlobDetector",
    "OnnxDetector",
    "TemplateDetector",
    "decode_yolov8",
    "letterbox",
    "non_max_suppression",
    "probe_vision",
    "select_providers",
    "to_model_input",
]
