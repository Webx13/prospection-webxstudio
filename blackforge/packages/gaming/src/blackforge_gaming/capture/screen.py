"""Capture d'écran via ``mss`` (Windows, Linux/X11, macOS), soumise à un consentement.

Garanties imposées par le code (testées) :
* aucune ouverture sans consentement actif couvrant l'affichage et la zone demandés ;
* consentement revérifié à CHAQUE lecture (expiration en cours de session) ;
* cadence plafonnée à ``consent.max_fps`` (la lecture se bloque pour la respecter) ;
* arrêt d'urgence vérifié avant chaque capture.

Limites connues :
* capture d'un affichage ou d'une zone fixe ; une fenêtre qui se déplace n'est pas suivie ;
* sous macOS, la permission « Enregistrement de l'écran » est accordée par l'OS, pas par ce
  code : sans elle, macOS ne renvoie PAS d'erreur mais une image sans le contenu des fenêtres.
  Utiliser ``probe_screen_capture()`` et la commande ``selfcheck`` pour le détecter ;
* ``mss`` doit être utilisé dans le thread qui l'a créé.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np

from blackforge_gaming.capture.base import CaptureUnavailableError, FrameSourceBase
from blackforge_gaming.consent import CaptureConsent, ConsentError, utc_now
from blackforge_gaming.core.capabilities import Availability, Capability
from blackforge_gaming.core.frame import Frame
from blackforge_gaming.core.geometry import Rect
from blackforge_gaming.core.safety import KillSwitch

audit = logging.getLogger("blackforge.gaming.audit")

BackendFactory = Callable[[], Any]


def _default_backend() -> Any:
    try:
        import mss
    except ImportError as exc:
        msg = "le paquet 'mss' est requis (extra « capture ») : uv sync --extra capture"
        raise CaptureUnavailableError(msg) from exc
    try:
        return mss.MSS()
    except Exception as exc:  # mss lève des erreurs spécifiques à chaque OS (X11, Quartz…)
        msg = f"impossible d'initialiser la capture d'écran : {type(exc).__name__}: {exc}"
        raise CaptureUnavailableError(msg) from exc


class ScreenCaptureSource(FrameSourceBase):
    def __init__(
        self,
        consent: CaptureConsent,
        *,
        region: Rect | None = None,
        kill_switch: KillSwitch | None = None,
        backend_factory: BackendFactory = _default_backend,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__()
        self._consent = consent
        self._region = region
        self._kill_switch = kill_switch
        self._backend_factory = backend_factory
        self._clock_ns = clock_ns
        self._sleep = sleep
        self._now = now
        self._backend: Any = None
        self._monitor: dict[str, int] = {}
        self._target: Rect | None = None
        self._frames_read = 0
        self._last_grab_ns: int | None = None

    @property
    def source_id(self) -> str:
        return f"screen:{self._consent.display_index}:{self._consent.consent_id[:8]}"

    def _open(self) -> None:
        self._consent.assert_active(self._now())
        backend = self._backend_factory()
        try:
            monitors = backend.monitors
            index = self._consent.display_index
            if not 1 <= index < len(monitors):
                msg = f"affichage {index} introuvable (disponibles : 1 à {len(monitors) - 1})"
                raise CaptureUnavailableError(msg)
            monitor = monitors[index]
            display = Rect(0, 0, int(monitor["width"]), int(monitor["height"]))
            target = self._region or display
            if not display.contains(target):
                msg = f"zone {target} hors de l'affichage {display.w}x{display.h}"
                raise ValueError(msg)
            if not self._consent.covers(index, target):
                msg = f"la zone {target} n'est pas couverte par le consentement accordé"
                raise ConsentError(msg)
        except BaseException:
            backend.close()
            raise
        self._backend = backend
        self._target = target
        self._monitor = {
            "left": int(monitor["left"]) + target.x,
            "top": int(monitor["top"]) + target.y,
            "width": target.w,
            "height": target.h,
        }
        audit.info(
            "capture_opened",
            extra={
                "consent_id": self._consent.consent_id,
                "purpose": self._consent.purpose,
                "granted_by": self._consent.granted_by,
                "display": index,
                "region": f"{target.x},{target.y},{target.w},{target.h}",
                "max_fps": self._consent.max_fps,
            },
        )

    def _throttle(self) -> None:
        if self._last_grab_ns is None:
            return
        min_interval_ns = int(1_000_000_000 / self._consent.max_fps)
        wait_ns = min_interval_ns - (self._clock_ns() - self._last_grab_ns)
        if wait_ns > 0:
            self._sleep(wait_ns / 1_000_000_000)

    def _guard(self) -> None:
        if self._kill_switch is not None:
            self._kill_switch.raise_if_triggered()
        self._consent.assert_active(self._now())

    def _read(self) -> Frame | None:
        self._guard()
        self._throttle()
        self._guard()  # le temps d'attente a pu laisser expirer le consentement ou déclencher l'arrêt
        target = self._target
        assert target is not None  # défini par _open()
        self._last_grab_ns = self._clock_ns()
        shot = self._backend.grab(self._monitor)
        width, height = int(shot.width), int(shot.height)
        bgra = np.frombuffer(shot.raw, dtype=np.uint8).reshape(height, width, 4)
        image = np.ascontiguousarray(bgra[:, :, :3])
        self._frames_read += 1
        return Frame(
            image=image,
            index=self._take_index(),
            captured_at_ns=self._clock_ns(),
            source_id=self.source_id,
            pixel_scale=width / self._monitor["width"],
            origin=(target.x, target.y),
            consent_id=self._consent.consent_id,
        )

    def _close(self) -> None:
        if self._backend is not None:
            self._backend.close()
            self._backend = None
        audit.info(
            "capture_closed",
            extra={"consent_id": self._consent.consent_id, "frames": self._frames_read},
        )


# --------------------------------------------------------------------------- capacités


def macos_screen_recording_permission() -> Availability:
    """Permission « Enregistrement de l'écran » (macOS 10.15+).

    NON VÉRIFIÉ sur un Mac réel : écrit d'après l'API CoreGraphics documentée
    (``CGPreflightScreenCaptureAccess``). Retourne UNKNOWN au moindre doute.
    """
    if sys.platform != "darwin":
        return Availability.NOT_APPLICABLE
    try:
        core_graphics = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        preflight = core_graphics.CGPreflightScreenCaptureAccess
        preflight.restype = ctypes.c_bool
        granted = bool(preflight())
    except (OSError, AttributeError):
        return Availability.UNKNOWN
    return Availability.AVAILABLE if granted else Availability.UNAVAILABLE


def probe_screen_capture(backend_factory: BackendFactory = _default_backend) -> list[Capability]:
    capabilities: list[Capability] = []
    try:
        backend = backend_factory()
    except CaptureUnavailableError as exc:
        capabilities.append(Capability("capture.screen", Availability.UNAVAILABLE, str(exc)))
    else:
        try:
            monitors = backend.monitors
            details = ", ".join(
                f"#{i}: {m['width']}x{m['height']}@({m['left']},{m['top']})"
                for i, m in enumerate(monitors)
                if i >= 1
            )
            capabilities.append(
                Capability("capture.screen", Availability.AVAILABLE, details or "aucun affichage")
            )
        finally:
            backend.close()
    permission = macos_screen_recording_permission()
    detail = {
        Availability.NOT_APPLICABLE: "propre à macOS",
        Availability.UNAVAILABLE: (
            "refusée : Réglages Système > Confidentialité > Enregistrement de l'écran"
        ),
        Availability.UNKNOWN: "état indéterminé (API indisponible)",
        Availability.AVAILABLE: "accordée",
    }[permission]
    capabilities.append(Capability("capture.macos_screen_recording", permission, detail))
    return capabilities
