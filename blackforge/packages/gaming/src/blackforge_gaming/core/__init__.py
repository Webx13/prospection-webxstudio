"""Contrats communs. N'importe que la bibliothèque standard et numpy."""

from blackforge_gaming.core.capabilities import Availability, Capability
from blackforge_gaming.core.detection import Detection, ScoreKind
from blackforge_gaming.core.frame import Frame
from blackforge_gaming.core.geometry import NormRect, Rect
from blackforge_gaming.core.protocols import Detector, FrameSource
from blackforge_gaming.core.safety import EmergencyStop, KillSwitch
from blackforge_gaming.core.types import Image

__all__ = [
    "Availability",
    "Capability",
    "Detection",
    "Detector",
    "EmergencyStop",
    "Frame",
    "FrameSource",
    "Image",
    "KillSwitch",
    "NormRect",
    "Rect",
    "ScoreKind",
]
