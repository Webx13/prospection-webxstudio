"""Bout en bout RÉEL : Xvfb (écran virtuel) + Chromium qui joue un jeu de test + capture ``mss``.

Rien n'est simulé ici : les pixels viennent d'un vrai navigateur affiché sur un vrai serveur X, la
capture passe par ``mss``, et les détections sont comparées à une vérité terrain exacte (la scène
du jeu de test est décrite par son URL).

Ce test ne s'exécute que sous Linux avec Xvfb et Chromium. Il ne prouve RIEN sur macOS ni Windows.
"""

from __future__ import annotations

import base64
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from blackforge_gaming.capture import (
    ReplaySource,
    ScreenCaptureSource,
    probe_screen_capture,
    record_frames,
)
from blackforge_gaming.cli import main
from blackforge_gaming.consent import CaptureConsent
from blackforge_gaming.core import Availability, EmergencyStop, Frame, KillSwitch, Rect
from blackforge_gaming.perception import ChangeDetector, DetectorBinding, PerceptionPipeline
from blackforge_gaming.vision import ColorBlobDetector, TemplateDetector
from tests.metrics import match_boxes
from tests.scenes import BACKGROUND, RED, sprite

pytestmark = pytest.mark.display

X11_SOCKETS = Path("/tmp/.X11-unix")  # noqa: S108 — répertoire standard des sockets X11
GAME = Path(__file__).parent / "fixtures" / "testgame" / "index.html"
SCREEN = (1280, 720)

# ----------------------------------------------------------------------- vérité terrain

RED_TRUTH = [Rect(200, 150, 60, 60), Rect(600, 300, 40, 40), Rect(900, 500, 80, 50)]
GREEN_TRUTH = [Rect(300, 400, 50, 50), Rect(1000, 100, 30, 30)]
SPRITE_TRUTH = [Rect(150, 500, 24, 24), Rect(700, 100, 24, 24), Rect(1100, 400, 24, 24)]
BLUE_DECOY = Rect(500, 600, 60, 60)  # aucun détecteur ne le cherche : il ne doit rien produire


def _rect(r: Rect, color: str) -> dict[str, object]:
    return {"t": "rect", "x": r.x, "y": r.y, "w": r.w, "h": r.h, "c": color}


def _sprite_item(r: Rect) -> dict[str, object]:
    bgr = sprite()
    rgba = np.dstack(
        [bgr[:, :, 2], bgr[:, :, 1], bgr[:, :, 0], np.full(bgr.shape[:2], 255, np.uint8)]
    )
    return {
        "t": "pixels",
        "x": r.x,
        "y": r.y,
        "w": bgr.shape[1],
        "h": bgr.shape[0],
        "rgba": base64.b64encode(rgba.tobytes()).decode(),
    }


SCENE_A: list[dict[str, object]] = [
    *(_rect(r, "#ff0000") for r in RED_TRUTH),
    *(_rect(r, "#00c800") for r in GREEN_TRUTH),
    _rect(BLUE_DECOY, "#0000ff"),
    *(_sprite_item(r) for r in SPRITE_TRUTH),
    {"t": "text", "x": 20, "y": 40, "s": "SCORE 120  HP 87", "c": "#ffffff"},
]

NEW_RED = Rect(400, 80, 150, 150)  # apparaît dans la scène B
SCENE_B: list[dict[str, object]] = [*SCENE_A, _rect(NEW_RED, "#ff0000")]


# ------------------------------------------------------------------------------ fixtures


def _chromium() -> str | None:
    if override := os.environ.get("BLACKFORGE_TEST_CHROMIUM"):
        return override if Path(override).exists() else None
    for pattern in ("/opt/pw-browsers/chromium-*/chrome-linux*/chrome",):
        if matches := sorted(glob.glob(pattern)):
            return matches[-1]
    return shutil.which("chromium") or shutil.which("google-chrome")


def _require_display_stack() -> None:
    if sys.platform != "linux":
        pytest.skip("test d'affichage virtuel : Linux uniquement")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb absent")
    if _chromium() is None:
        pytest.skip("Chromium absent (définir BLACKFORGE_TEST_CHROMIUM)")


def _start_xvfb() -> tuple[subprocess.Popen[bytes], str]:
    number = next(n for n in range(90, 200) if not (X11_SOCKETS / f"X{n}").exists())
    display = f":{number}"
    server = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", f"{SCREEN[0]}x{SCREEN[1]}x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not (X11_SOCKETS / f"X{number}").exists():
        if time.monotonic() > deadline or server.poll() is not None:
            server.kill()
            pytest.fail("Xvfb n'a pas démarré")
        time.sleep(0.05)
    return server, display


def _stop_xvfb(server: subprocess.Popen[bytes]) -> None:
    os.killpg(server.pid, signal.SIGTERM)
    server.wait(timeout=10)


@pytest.fixture(scope="module")
def xvfb() -> Iterator[str]:
    _require_display_stack()
    server, display = _start_xvfb()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DISPLAY", display)
        try:
            yield display
        finally:
            _stop_xvfb(server)


@pytest.fixture
def private_display(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Un écran virtuel exclusif : aucun autre navigateur ne vient perturber la mesure."""
    _require_display_stack()
    server, display = _start_xvfb()
    monkeypatch.setenv("DISPLAY", display)
    try:
        yield display
    finally:
        _stop_xvfb(server)


def _launch(
    scene_a: list[dict[str, object]],
    profile: Path,
    scene_b: list[dict[str, object]] | None = None,
    delay_ms: int = 0,
) -> subprocess.Popen[bytes]:
    fragment = "a=" + urllib.parse.quote(json.dumps(scene_a))
    if scene_b is not None:
        fragment += "&b=" + urllib.parse.quote(json.dumps(scene_b)) + f"&delay={delay_ms}"
    chromium = _chromium()
    assert chromium is not None
    return subprocess.Popen(
        [
            chromium,
            "--no-sandbox",  # exécution en root dans le conteneur de test
            "--kiosk",
            "--window-position=0,0",
            f"--window-size={SCREEN[0]},{SCREEN[1]}",
            f"--user-data-dir={profile}",
            "--force-device-scale-factor=1",
            "--disable-gpu",
            "--no-first-run",
            "--disable-infobars",
            # Un test ne doit pas « téléphoner » : aucune connexion de fond vers les services du navigateur.
            # Hermétique : plus aucune résolution DNS (la page de test est un fichier local).
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--no-pings",
            "--disable-default-apps",
            f"{GAME.as_uri()}#{fragment}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _stop(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)


def _consent(**overrides: object) -> CaptureConsent:
    params: dict[str, object] = {
        "purpose": "tester BLACKFORGE sur son propre jeu de test",
        "granted_by": "pytest",
        "display_index": 1,
        "duration": timedelta(minutes=5),
        "max_fps": 30.0,
    }
    params.update(overrides)
    return CaptureConsent.grant(**params)  # type: ignore[arg-type]


def _wait_until_rendered(source: ScreenCaptureSource, timeout_s: float = 25.0) -> Frame:
    """Capture jusqu'à ce que le jeu soit réellement affiché (fond #101018 en haut à gauche)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = source.read()
        assert frame is not None
        if tuple(frame.image[0, 0]) == BACKGROUND and tuple(frame.image[150, 230]) == RED:
            return frame
        time.sleep(0.1)
    pytest.fail("le jeu de test ne s'est pas affiché à temps")


@pytest.fixture(scope="module")
def static_game(xvfb: str, tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    process = _launch(SCENE_A, tmp_path_factory.mktemp("chrome-static"))
    try:
        with ScreenCaptureSource(_consent()) as source:
            _wait_until_rendered(source)
        yield
    finally:
        _stop(process)


def _pipeline(change: ChangeDetector | None = None) -> PerceptionPipeline:
    # min_area écarte les cellules rouges des sprites (4 px) : sans lui, elles sont détectées.
    red = ColorBlobDetector(
        name="red", label="enemy", hsv_lower=(170, 120, 120), hsv_upper=(10, 255, 255), min_area=400
    )
    green = ColorBlobDetector(
        name="green", label="ally", hsv_lower=(45, 120, 120), hsv_upper=(75, 255, 255), min_area=400
    )
    hero = TemplateDetector(name="hero", label="hero", template=sprite(), threshold=0.95)
    return PerceptionPipeline(
        [DetectorBinding(red), DetectorBinding(green), DetectorBinding(hero)],
        change_detector=change,
    )


def _boxes(perception_detections: tuple, label: str) -> list[Rect]:  # type: ignore[type-arg]
    return [d.box for d in perception_detections if d.label == label]


# ------------------------------------------------------------------------------- tests


def test_probe_sees_the_real_virtual_display(static_game: None) -> None:
    capability = next(c for c in probe_screen_capture() if c.name == "capture.screen")
    assert capability.availability is Availability.AVAILABLE
    assert f"{SCREEN[0]}x{SCREEN[1]}" in capability.detail


def test_real_capture_returns_the_exact_pixels_of_the_game(static_game: None) -> None:
    consent = _consent()
    with ScreenCaptureSource(consent) as source:
        frame = source.read()
    assert frame is not None
    assert (frame.width, frame.height) == SCREEN
    assert frame.pixel_scale == 1.0 and frame.consent_id == consent.consent_id
    for rect in RED_TRUTH:  # chaque carré rouge est capturé au pixel près
        region = frame.crop(rect)
        assert (region == RED).all(), f"pixels inattendus dans {rect}"
    assert tuple(frame.image[0, 0]) == BACKGROUND


def test_perception_on_real_capture_matches_ground_truth(static_game: None) -> None:
    pipeline = _pipeline()
    latencies, capture_ms = [], []
    with ScreenCaptureSource(_consent(max_fps=60.0)) as source:
        for _ in range(15):
            t0 = time.perf_counter()
            frame = source.read()
            capture_ms.append((time.perf_counter() - t0) * 1000)
            assert frame is not None
            perception = pipeline.process(frame)
            latencies.append(perception.total_ms)
    assert perception.analyzed and not perception.degraded

    red = match_boxes(RED_TRUTH, _boxes(perception.detections, "enemy"))
    green = match_boxes(GREEN_TRUTH, _boxes(perception.detections, "ally"))
    hero = match_boxes(SPRITE_TRUTH, _boxes(perception.detections, "hero"))
    for name, result in (("red", red), ("green", green), ("hero", hero)):
        assert result.precision == 1.0, f"{name}: faux positifs {result}"
        assert result.recall == 1.0, f"{name}: objets manqués {result}"
        assert result.mean_iou >= 0.95, f"{name}: boîtes imprécises {result}"
    hero_scores = [d.confidence for d in perception.detections if d.label == "hero"]
    assert min(hero_scores) >= 0.95 and all(
        d.score_kind == "similarity" for d in perception.detections if d.label == "hero"
    )
    assert not any(
        d.box.iou(BLUE_DECOY) > 0 for d in perception.detections
    )  # le leurre reste invisible

    summary = pipeline.latency_summary()
    assert summary is not None and summary.p95_ms < 1000
    print(
        "METRICS",
        json.dumps(
            {
                "resolution": SCREEN,
                "frames": len(latencies),
                "perception_ms": {"p50": round(summary.p50_ms, 1), "p95": round(summary.p95_ms, 1)},
                "capture_ms_median": round(float(np.median(capture_ms)), 1),
                "red": [
                    red.true_positives,
                    red.false_positives,
                    red.false_negatives,
                    round(red.mean_iou, 3),
                ],
                "green": [
                    green.true_positives,
                    green.false_positives,
                    green.false_negatives,
                    round(green.mean_iou, 3),
                ],
                "hero": [
                    hero.true_positives,
                    hero.false_positives,
                    hero.false_negatives,
                    round(hero.mean_iou, 3),
                ],
            }
        ),
    )


def test_region_capture_is_a_pixel_exact_crop_of_the_full_screen(static_game: None) -> None:
    zone = Rect(180, 130, 120, 100)  # contient le 1er carré rouge à (20, 20) relatif
    consent = _consent(region=Rect(100, 100, 400, 300))
    with ScreenCaptureSource(_consent()) as full, ScreenCaptureSource(consent, region=zone) as part:
        whole = full.read()
        cropped = part.read()
    assert whole is not None and cropped is not None
    assert cropped.origin == (180, 130)
    assert np.array_equal(cropped.image, whole.crop(zone))
    detector = ColorBlobDetector(
        name="r", label="e", hsv_lower=(170, 120, 120), hsv_upper=(10, 255, 255)
    )
    assert [d.box for d in detector.detect(cropped.image)] == [Rect(20, 20, 60, 60)]


def test_event_driven_analysis_on_a_real_changing_screen(
    private_display: str, tmp_path: Path
) -> None:
    """Le jeu ajoute un carré rouge après ~3 s : les images identiques sont ignorées, le
    changement réel est détecté et analysé, avec la boîte exacte du nouvel objet."""
    process = _launch(SCENE_A, tmp_path / "profile", scene_b=SCENE_B, delay_ms=3000)
    pipeline = _pipeline(ChangeDetector(threshold=0.002))
    analyzed_flags: list[bool] = []
    scores: list[float | None] = []
    final = None
    try:
        with ScreenCaptureSource(_consent(max_fps=20.0)) as source:
            _wait_until_rendered(source)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                frame = source.read()
                assert frame is not None
                perception = pipeline.process(frame)
                analyzed_flags.append(perception.analyzed)
                scores.append(perception.change_score)
                # Une analyse à score nul est le rafraîchissement forcé (max_stale_frames), pas
                # le changement de scène : on attend une analyse DÉCLENCHÉE par un changement.
                if (
                    perception.analyzed
                    and (perception.change_score or 0.0) > 0.002
                    and len(analyzed_flags) > 1
                ):
                    final = perception
                    break
    finally:
        _stop(process)
    assert final is not None, "le changement de scène n'a pas été détecté"
    assert analyzed_flags[0] is True
    assert analyzed_flags.count(False) >= 5, (
        f"les images identiques auraient dû être ignorées : {list(zip(analyzed_flags, scores, strict=True))}"
    )
    assert final.change_score is not None and final.change_score > 0.002
    reds = _boxes(final.detections, "enemy")
    assert match_boxes([*RED_TRUTH, NEW_RED], reds).recall == 1.0
    assert match_boxes([*RED_TRUTH, NEW_RED], reds).precision == 1.0


def test_recorded_real_frames_replay_to_identical_detections(
    static_game: None, tmp_path: Path
) -> None:
    pipeline = _pipeline()
    with ScreenCaptureSource(_consent()) as source:
        assert record_frames(source, tmp_path / "rec", max_frames=3) == 3
        live = pipeline.process(source.read())  # type: ignore[arg-type]
    with ReplaySource(tmp_path / "rec") as replay:
        frames = []
        while (frame := replay.read()) is not None:
            frames.append(frame)
    assert len(frames) == 3
    replayed = _pipeline().process(frames[-1])
    assert sorted(live.detections, key=lambda d: (d.label, d.box.y, d.box.x)) == sorted(
        replayed.detections, key=lambda d: (d.label, d.box.y, d.box.x)
    )
    assert frames[0].source_id.startswith("replay:") and frames[0].consent_id is None


def test_kill_switch_stops_a_real_capture(static_game: None) -> None:
    kill = KillSwitch()
    with ScreenCaptureSource(_consent(), kill_switch=kill) as source:
        assert source.read() is not None
        kill.trigger("arrêt d'urgence")
        with pytest.raises(EmergencyStop):
            source.read()


def test_cli_selfcheck_on_the_real_display(
    static_game: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "check.png"
    assert main(["selfcheck-capture", "--i-consent", "--out", str(out)]) == 0
    stdout = capsys.readouterr().out
    assert "1280x720" in stdout and out.stat().st_size > 1000
    assert "uniforme" not in stdout
