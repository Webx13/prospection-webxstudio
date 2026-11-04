"""Perception Engine : orchestre des détecteurs injectés et produit un état perçu structuré."""

from blackforge_gaming.perception.change import ChangeDetector
from blackforge_gaming.perception.pipeline import (
    DetectorBinding,
    DetectorError,
    Perception,
    PerceptionPipeline,
    RegionOfInterest,
    StageTiming,
)
from blackforge_gaming.perception.stats import LatencySummary, RollingStats

__all__ = [
    "ChangeDetector",
    "DetectorBinding",
    "DetectorError",
    "LatencySummary",
    "Perception",
    "PerceptionPipeline",
    "RegionOfInterest",
    "RollingStats",
    "StageTiming",
]
