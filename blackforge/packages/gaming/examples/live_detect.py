"""Capture VOTRE écran (avec consentement explicite) et détecte des carrés rouges.

    uv run python examples/live_detect.py --i-consent --frames 20

Aucune image n'est enregistrée ni envoyée : tout est traité localement, en mémoire.
Interrompez à tout moment avec Ctrl+C (arrêt d'urgence → la capture s'arrête immédiatement).
"""

from __future__ import annotations

import argparse
import signal
import sys
from datetime import timedelta
from types import FrameType

from blackforge_gaming.capture import CaptureUnavailableError, ScreenCaptureSource
from blackforge_gaming.consent import CaptureConsent
from blackforge_gaming.core import EmergencyStop, KillSwitch
from blackforge_gaming.perception import ChangeDetector, DetectorBinding, PerceptionPipeline
from blackforge_gaming.vision import ColorBlobDetector


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--display", type=int, default=1)
    parser.add_argument("--i-consent", action="store_true", help="autorise la capture de l'écran")
    args = parser.parse_args()
    if not args.i_consent:
        print("Ajoutez --i-consent pour autoriser la capture de votre écran.", file=sys.stderr)
        return 2

    consent = CaptureConsent.grant(
        purpose="démo de détection sur mon propre jeu",
        granted_by="utilisateur local",
        display_index=args.display,
        duration=timedelta(minutes=2),
        max_fps=10.0,
    )
    kill_switch = KillSwitch()

    def on_sigint(_signum: int, _frame: FrameType | None) -> None:
        kill_switch.trigger("Ctrl+C")

    signal.signal(signal.SIGINT, on_sigint)

    red = ColorBlobDetector(
        name="red",
        label="enemy",
        hsv_lower=(170, 120, 120),  # teinte qui « fait le tour » : le rouge est à cheval sur 0/179
        hsv_upper=(10, 255, 255),
        min_area=400,  # écarte les petits éléments rouges (sprites, texte)
    )
    pipeline = PerceptionPipeline(
        [DetectorBinding(red)],
        change_detector=ChangeDetector(threshold=0.002),  # n'analyse que si l'écran a changé
    )
    try:
        with ScreenCaptureSource(consent, kill_switch=kill_switch) as source:
            for _ in range(args.frames):
                frame = source.read()
                assert frame is not None
                result = pipeline.process(frame)
                boxes = [(d.box.x, d.box.y, d.box.w, d.box.h) for d in result.detections]
                state = "analysée" if result.analyzed else "inchangée (ignorée)"
                print(
                    f"image {frame.index:3d} {state:<20} {result.total_ms:6.1f} ms  ennemis={boxes}"
                )
    except CaptureUnavailableError as exc:
        print(f"Capture impossible : {exc}", file=sys.stderr)
        return 1
    except EmergencyStop as exc:
        print(f"Arrêté : {exc}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
