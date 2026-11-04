"""Géométrie 2D : rectangles en pixels et en coordonnées normalisées (indépendantes de la résolution)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    """Rectangle en pixels entiers. Origine en haut à gauche, ``x2``/``y2`` exclus."""

    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            msg = f"Rect doit avoir une taille strictement positive, reçu {self.w}x{self.h}"
            raise ValueError(msg)

    @classmethod
    def from_xyxy(cls, x1: int, y1: int, x2: int, y2: int) -> Rect:
        return cls(x1, y1, x2 - x1, y2 - y1)

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def intersection(self, other: Rect) -> Rect | None:
        x1, y1 = max(self.x, other.x), max(self.y, other.y)
        x2, y2 = min(self.x2, other.x2), min(self.y2, other.y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return Rect(x1, y1, x2 - x1, y2 - y1)

    def iou(self, other: Rect) -> float:
        inter = self.intersection(other)
        if inter is None:
            return 0.0
        return inter.area / (self.area + other.area - inter.area)

    def contains(self, other: Rect) -> bool:
        return (
            self.x <= other.x and self.y <= other.y and self.x2 >= other.x2 and self.y2 >= other.y2
        )

    def translated(self, dx: int, dy: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def clamped(self, width: int, height: int) -> Rect | None:
        """Partie du rectangle située dans ``[0,width) x [0,height)``, ou ``None``."""
        return self.intersection(Rect(0, 0, width, height))


@dataclass(frozen=True, slots=True)
class NormRect:
    """Rectangle en fractions de la taille de l'image (0..1) : valable à toute résolution."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        eps = 1e-9
        if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
            msg = "NormRect: x et y doivent être dans [0, 1]"
            raise ValueError(msg)
        if self.w <= 0.0 or self.h <= 0.0:
            msg = "NormRect: w et h doivent être strictement positifs"
            raise ValueError(msg)
        if self.x + self.w > 1.0 + eps or self.y + self.h > 1.0 + eps:
            msg = "NormRect: le rectangle dépasse de l'image"
            raise ValueError(msg)

    def to_rect(self, width: int, height: int) -> Rect:
        """Résout le rectangle pour une image ``width`` x ``height`` (au moins 1 pixel)."""
        x1 = min(round(self.x * width), width - 1)
        y1 = min(round(self.y * height), height - 1)
        x2 = min(max(round((self.x + self.w) * width), x1 + 1), width)
        y2 = min(max(round((self.y + self.h) * height), y1 + 1), height)
        return Rect(x1, y1, x2 - x1, y2 - y1)
