"""Enregistrement et rejeu de captures : base du Training Lab (tests reproductibles, sans jeu lancé).

Format sur disque : un dossier contenant ``frame_000000.png`` … et ``manifest.json``.
PNG sans perte : les détections sur rejeu sont identiques à celles du direct.

Horodatage au rejeu : ``captured_at_ns`` suit l'horloge enregistrée (``recorded_ns``) si elle est
dans le manifeste ; c'est une horloge VIRTUELLE, jamais l'heure réelle de lecture.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

import numpy as np

from blackforge_gaming.capture.base import CaptureUnavailableError, FrameSourceBase
from blackforge_gaming.core.frame import Frame
from blackforge_gaming.core.protocols import FrameSource
from blackforge_gaming.core.safety import KillSwitch

MANIFEST_NAME: Final = "manifest.json"
MANIFEST_VERSION: Final = 1


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        msg = "OpenCV est requis pour le rejeu (extra « vision ») : uv sync --extra vision"
        raise CaptureUnavailableError(msg) from exc
    return cv2


def record_frames(source: FrameSource, directory: Path, *, max_frames: int) -> int:
    """Enregistre jusqu'à ``max_frames`` images de ``source`` ; retourne le nombre écrit.

    La source doit déjà être ouverte (donc déjà soumise à son propre consentement).
    """
    if max_frames <= 0:
        msg = "max_frames doit être > 0"
        raise ValueError(msg)
    cv2 = _cv2()
    directory.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    first_ns: int | None = None
    while len(entries) < max_frames:
        frame = source.read()
        if frame is None:
            break
        first_ns = frame.captured_at_ns if first_ns is None else first_ns
        name = f"frame_{len(entries):06d}.png"
        if not cv2.imwrite(str(directory / name), frame.image, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
            msg = f"écriture impossible : {directory / name}"
            raise OSError(msg)
        entries.append(
            {
                "file": name,
                "recorded_ns": frame.captured_at_ns - first_ns,
                "pixel_scale": frame.pixel_scale,
                "origin": list(frame.origin),
            }
        )
    manifest = {"version": MANIFEST_VERSION, "source_id": source.source_id, "frames": entries}
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return len(entries)


class ReplaySource(FrameSourceBase):
    """Rejoue un dossier produit par ``record_frames`` (ou une liste d'images PNG ordonnée)."""

    def __init__(
        self,
        directory: Path,
        *,
        fps: float = 30.0,
        loop: bool = False,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        super().__init__()
        if fps <= 0:
            msg = "fps doit être > 0"
            raise ValueError(msg)
        self._directory = directory
        self._fps = fps
        self._loop = loop
        self._kill_switch = kill_switch
        self._entries: list[dict[str, Any]] = []
        self._cursor = 0

    @property
    def source_id(self) -> str:
        return f"replay:{self._directory.name}"

    def __len__(self) -> int:
        return len(self._entries)

    def _open(self) -> None:
        if not self._directory.is_dir():
            msg = f"dossier de rejeu introuvable : {self._directory}"
            raise CaptureUnavailableError(msg)
        manifest_path = self._directory / MANIFEST_NAME
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != MANIFEST_VERSION:
                msg = f"version de manifeste non supportée : {manifest.get('version')}"
                raise CaptureUnavailableError(msg)
            self._entries = list(manifest["frames"])
        else:
            files: Iterable[Path] = sorted(self._directory.glob("*.png"))
            self._entries = [{"file": f.name} for f in files]
        if not self._entries:
            msg = f"aucune image dans {self._directory}"
            raise CaptureUnavailableError(msg)
        self._cursor = 0
        self._next_index = 0

    def _read(self) -> Frame | None:
        if self._kill_switch is not None:
            self._kill_switch.raise_if_triggered()
        if self._cursor >= len(self._entries):
            if not self._loop:
                return None
            self._cursor = 0
        entry = self._entries[self._cursor]
        path = self._directory / str(entry["file"])
        # imdecode(fromfile) plutôt qu'imread : gère les chemins non ASCII sur tous les OS.
        data = np.fromfile(path, dtype=np.uint8)
        image = _cv2().imdecode(data, _cv2().IMREAD_COLOR)
        if image is None:
            msg = f"image illisible : {path}"
            raise CaptureUnavailableError(msg)
        index = self._take_index()
        recorded_ns = entry.get("recorded_ns")
        captured_ns = int(recorded_ns) if recorded_ns is not None else int(index * 1e9 / self._fps)
        self._cursor += 1
        return Frame(
            image=image,
            index=index,
            captured_at_ns=captured_ns,
            source_id=self.source_id,
            pixel_scale=float(entry.get("pixel_scale", 1.0)),
            origin=(int(entry.get("origin", [0, 0])[0]), int(entry.get("origin", [0, 0])[1])),
        )

    def _close(self) -> None:
        self._entries = []
