"""Outils en ligne de commande : ``blackforge-gaming probe`` et ``blackforge-gaming selfcheck-capture``."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import numpy as np

from blackforge_gaming.capture import CaptureUnavailableError, ScreenCaptureSource
from blackforge_gaming.consent import CaptureConsent, ConsentError
from blackforge_gaming.core.geometry import Rect
from blackforge_gaming.probe import build_report


def _parse_region(text: str) -> Rect:
    try:
        x, y, w, h = (int(part) for part in text.split(","))
        return Rect(x, y, w, h)
    except ValueError as exc:
        msg = "--region attend x,y,largeur,hauteur (entiers, largeur et hauteur > 0)"
        raise argparse.ArgumentTypeError(msg) from exc


def _probe(args: argparse.Namespace) -> int:
    report = build_report()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0
    print(f"Plateforme : {report.platform} ({report.machine}) — Python {report.python}")
    for cap in report.capabilities:
        print(f"  [{cap.availability.value:>14}] {cap.name}  {cap.detail}")
    return 0


def _selfcheck(args: argparse.Namespace) -> int:
    if not args.i_consent:
        print(
            "Cette commande capture VOTRE écran (une seule image, non transmise).\n"
            "Relancez avec --i-consent pour confirmer.",
            file=sys.stderr,
        )
        return 2
    consent = CaptureConsent.grant(
        purpose="auto-diagnostic de la capture",
        granted_by=f"cli:{getpass.getuser()}",
        display_index=args.display,
        duration=timedelta(seconds=60),
        max_fps=1.0,
        region=args.region,
    )
    try:
        with ScreenCaptureSource(consent, region=args.region) as source:
            frame = source.read()
    except (CaptureUnavailableError, ConsentError, ValueError) as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        return 1
    assert frame is not None
    means = frame.image.reshape(-1, 3).mean(axis=0)
    spread = float(frame.image.std())
    print(f"Image : {frame.width}x{frame.height} px, pixel_scale={frame.pixel_scale}")
    print(f"Moyenne BGR : {np.round(means, 1).tolist()}  écart-type global : {spread:.1f}")
    verdict = 0
    if spread < 1.0:
        print(
            "ATTENTION : image quasi uniforme. Écran noir ? Sous macOS, la permission "
            "« Enregistrement de l'écran » est probablement manquante (l'OS ne signale pas d'erreur).",
            file=sys.stderr,
        )
        verdict = 3
    if args.out:
        import cv2

        path = Path(args.out)
        if not cv2.imwrite(str(path), frame.image):
            print(f"ÉCHEC : écriture impossible de {path}", file=sys.stderr)
            return 1
        print(f"Image enregistrée : {path}")
    return verdict


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="blackforge-gaming")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="liste les capacités réelles de cette machine")
    probe.add_argument("--json", action="store_true", help="sortie JSON")
    probe.set_defaults(func=_probe)

    check = sub.add_parser("selfcheck-capture", help="capture UNE image pour vérifier la capture")
    check.add_argument("--display", type=int, default=1, help="numéro d'affichage (1 = principal)")
    check.add_argument("--region", type=_parse_region, default=None, help="x,y,largeur,hauteur")
    check.add_argument("--out", default=None, help="enregistre l'image capturée (PNG)")
    check.add_argument(
        "--i-consent", action="store_true", help="confirme la capture de votre écran"
    )
    check.set_defaults(func=_selfcheck)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
