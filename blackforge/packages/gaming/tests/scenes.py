"""Images synthétiques à vérité terrain connue (données de test, pas des « fausses » fonctions)."""

from __future__ import annotations

import numpy as np

from blackforge_gaming.core.geometry import Rect
from blackforge_gaming.core.types import Image

BACKGROUND = (24, 16, 16)  # BGR de #101018
RED = (0, 0, 255)
GREEN = (0, 200, 0)
BLUE = (255, 0, 0)


def blank(width: int = 320, height: int = 180, color: tuple[int, int, int] = BACKGROUND) -> Image:
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = color
    return image


def fill(image: Image, rect: Rect, color: tuple[int, int, int]) -> None:
    image[rect.y : rect.y2, rect.x : rect.x2] = color


def sprite(cells: int = 12, cell_px: int = 2, seed: int = 7) -> Image:
    """Sprite pixel-art asymétrique et déterministe (pas de symétrie qui fausserait la corrélation)."""
    rng = np.random.default_rng(seed)
    palette = np.array([(30, 30, 200), (40, 180, 220), (220, 220, 220), (180, 60, 60)], np.uint8)
    grid = palette[rng.integers(0, len(palette), size=(cells, cells))]
    return np.repeat(np.repeat(grid, cell_px, axis=0), cell_px, axis=1)


def paste(image: Image, sprite_image: Image, x: int, y: int) -> Rect:
    h, w = sprite_image.shape[:2]
    image[y : y + h, x : x + w] = sprite_image
    return Rect(x, y, w, h)
