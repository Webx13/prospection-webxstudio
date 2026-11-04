"""Consentement + capture d'écran, avec un faux backend ``mss`` (double de test, pas une fausse
fonctionnalité : la capture RÉELLE est vérifiée dans test_e2e_display.py)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from blackforge_gaming.capture import CaptureUnavailableError, ScreenCaptureSource
from blackforge_gaming.consent import CaptureConsent, ConsentError
from blackforge_gaming.core import EmergencyStop, FrameSource, KillSwitch, Rect

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def consent(**overrides: object) -> CaptureConsent:
    params: dict[str, object] = {
        "purpose": "tester mon propre jeu",
        "granted_by": "alice",
        "display_index": 1,
        "duration": timedelta(minutes=10),
        "max_fps": 10.0,
        "now": T0,
    }
    params.update(overrides)
    return CaptureConsent.grant(**params)  # type: ignore[arg-type]


# ------------------------------------------------------------------------ consentement


def test_consent_is_active_only_inside_its_window() -> None:
    c = consent()
    assert c.is_active(T0)
    assert c.is_active(T0 + timedelta(minutes=9, seconds=59))
    assert not c.is_active(T0 + timedelta(minutes=10))
    assert not c.is_active(T0 - timedelta(seconds=1))
    with pytest.raises(ConsentError):
        c.assert_active(T0 + timedelta(hours=1))


def test_consent_rejects_naive_datetimes_and_inverted_window() -> None:
    with pytest.raises(ValidationError, match="fuseau"):
        CaptureConsent(
            purpose="test jeu",
            granted_by="a",
            display_index=1,
            granted_at=datetime(2026, 1, 1),
            expires_at=datetime(2026, 1, 2),
            max_fps=10,
        )
    with pytest.raises(ValidationError, match="postérieur"):
        CaptureConsent(
            purpose="test jeu",
            granted_by="a",
            display_index=1,
            granted_at=T0,
            expires_at=T0 - timedelta(seconds=1),
            max_fps=10,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"display_index": 0},  # « tous les écrans » refusé : moindre privilège
        {"max_fps": 0},
        {"max_fps": 1000},
        {"purpose": "x"},
        {"granted_by": ""},
    ],
)
def test_consent_rejects_overbroad_or_empty_grants(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        consent(**overrides)


def test_consent_is_immutable() -> None:
    c = consent()
    with pytest.raises(ValidationError):
        c.max_fps = 240  # type: ignore[misc]


def test_consent_covers_display_and_region() -> None:
    whole = consent()
    assert whole.covers(1, Rect(0, 0, 1920, 1080))
    assert not whole.covers(2, Rect(0, 0, 10, 10))
    zone = consent(region=Rect(100, 100, 400, 300))
    assert zone.covers(1, Rect(150, 150, 100, 100))
    assert zone.covers(1, Rect(100, 100, 400, 300))
    assert not zone.covers(1, Rect(0, 0, 1920, 1080))
    assert not zone.covers(1, Rect(450, 350, 100, 100))  # dépasse du périmètre accordé


# ----------------------------------------------------------------------------- faux mss


@dataclass
class FakeShot:
    raw: bytearray
    width: int
    height: int


class FakeBackend:
    """Imite ``mss.mss()`` : un écran 1920x1080 ; ``scale`` simule un écran Retina."""

    def __init__(self, scale: int = 1, color_bgra: tuple[int, int, int, int] = (10, 20, 30, 255)):
        self.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},  # [0] = tous les écrans
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]
        self.scale = scale
        self.color = color_bgra
        self.grabs: list[dict[str, int]] = []
        self.closed = False

    def grab(self, monitor: dict[str, int]) -> FakeShot:
        self.grabs.append(dict(monitor))
        w, h = monitor["width"] * self.scale, monitor["height"] * self.scale
        data = np.empty((h, w, 4), dtype=np.uint8)
        data[:] = self.color
        return FakeShot(bytearray(data.tobytes()), w, h)

    def close(self) -> None:
        self.closed = True


class Clock:
    """Horloge et sommeil virtuels : le test ne dort jamais pour de vrai."""

    def __init__(self) -> None:
        self.ns = 1_000_000_000
        self.slept: list[float] = []
        self.wall = T0

    def clock_ns(self) -> int:
        return self.ns

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.ns += int(seconds * 1e9)
        self.wall += timedelta(seconds=seconds)

    def now(self) -> datetime:
        return self.wall


def source(
    c: CaptureConsent,
    backend: FakeBackend,
    clock: Clock,
    *,
    region: Rect | None = None,
    kill: KillSwitch | None = None,
) -> ScreenCaptureSource:
    return ScreenCaptureSource(
        c,
        region=region,
        kill_switch=kill,
        backend_factory=lambda: backend,
        clock_ns=clock.clock_ns,
        sleep=clock.sleep,
        now=clock.now,
    )


# ------------------------------------------------------------------------------ capture


def test_screen_source_satisfies_the_frame_source_protocol() -> None:
    assert isinstance(source(consent(), FakeBackend(), Clock()), FrameSource)


def test_read_converts_bgra_to_contiguous_bgr_with_metadata() -> None:
    clock, backend = Clock(), FakeBackend()
    c = consent()
    with source(c, backend, clock) as src:
        frame = src.read()
    assert frame is not None
    assert frame.image.shape == (1080, 1920, 3)
    assert frame.image.flags["C_CONTIGUOUS"]
    assert tuple(frame.image[0, 0]) == (
        10,
        20,
        30,
    )  # le canal alpha a disparu, l'ordre BGR est conservé
    assert (frame.index, frame.pixel_scale, frame.origin) == (0, 1.0, (0, 0))
    assert frame.consent_id == c.consent_id
    assert frame.source_id.startswith("screen:1:")
    assert backend.closed


def test_retina_scale_is_detected_from_the_returned_pixels() -> None:
    with source(consent(), FakeBackend(scale=2), Clock()) as src:
        frame = src.read()
    assert frame is not None
    assert frame.pixel_scale == 2.0
    assert (frame.width, frame.height) == (3840, 2160)


def test_region_is_grabbed_with_display_offset_and_reported_as_origin() -> None:
    backend = FakeBackend()
    c = consent(display_index=2, region=Rect(100, 50, 640, 360))
    with source(c, backend, Clock(), region=Rect(110, 60, 200, 100)) as src:
        frame = src.read()
    assert backend.grabs == [{"left": 1920 + 110, "top": 60, "width": 200, "height": 100}]
    assert frame is not None
    assert frame.origin == (110, 60)
    assert (frame.width, frame.height) == (200, 100)


def test_open_refuses_an_expired_consent() -> None:
    clock = Clock()
    clock.wall = T0 + timedelta(hours=1)
    with pytest.raises(ConsentError):
        source(consent(), FakeBackend(), clock).open()


def test_open_refuses_a_region_outside_the_consent() -> None:
    c = consent(region=Rect(0, 0, 400, 300))
    backend = FakeBackend()
    with pytest.raises(ConsentError, match="couverte"):
        source(c, backend, Clock(), region=Rect(300, 200, 400, 300)).open()
    assert backend.closed  # pas de fuite de ressource sur échec d'ouverture


def test_open_refuses_a_whole_display_when_consent_is_a_region() -> None:
    with pytest.raises(ConsentError):
        source(consent(region=Rect(0, 0, 400, 300)), FakeBackend(), Clock()).open()


def test_open_rejects_a_region_outside_the_display() -> None:
    with pytest.raises(ValueError, match="hors de l'affichage"):
        source(consent(), FakeBackend(), Clock(), region=Rect(1900, 1000, 100, 100)).open()


def test_open_reports_a_missing_display() -> None:
    with pytest.raises(CaptureUnavailableError, match="affichage 3 introuvable"):
        source(consent(display_index=3), FakeBackend(), Clock()).open()


def test_frame_rate_is_capped_by_the_consent() -> None:
    clock = Clock()
    with source(consent(max_fps=10.0), FakeBackend(), clock) as src:
        for _ in range(4):
            src.read()
    assert len(clock.slept) == 3  # la 1re lecture n'attend pas
    assert all(s == pytest.approx(0.1, abs=1e-6) for s in clock.slept)


def test_consent_is_rechecked_on_every_read() -> None:
    clock = Clock()
    c = consent(duration=timedelta(seconds=5))
    with source(c, FakeBackend(), clock) as src:
        assert src.read() is not None
        clock.wall = T0 + timedelta(seconds=6)  # expire en cours de session
        with pytest.raises(ConsentError):
            src.read()


def test_throttle_wait_cannot_outlive_the_consent() -> None:
    clock = Clock()
    c = consent(
        duration=timedelta(milliseconds=50), max_fps=1.0
    )  # 1 s d'attente > 50 ms de validité
    with source(c, FakeBackend(), clock) as src:
        src.read()
        with pytest.raises(ConsentError):
            src.read()


def test_kill_switch_stops_capture_before_any_grab() -> None:
    backend, kill = FakeBackend(), KillSwitch()
    with source(consent(), backend, Clock(), kill=kill) as src:
        assert src.read() is not None
        grabs_before = len(backend.grabs)
        kill.trigger("arrêt d'urgence utilisateur")
        with pytest.raises(EmergencyStop):
            src.read()
        assert len(backend.grabs) == grabs_before


def test_lifecycle_is_safe() -> None:
    src = source(consent(), FakeBackend(), Clock())
    with pytest.raises(RuntimeError, match="avant open"):
        src.read()
    src.open()
    src.open()  # idempotent
    src.close()
    src.close()  # idempotent


def test_audit_log_records_consent_but_never_pixels(caplog: pytest.LogCaptureFixture) -> None:
    c = consent()
    with (
        caplog.at_level(logging.INFO, logger="blackforge.gaming.audit"),
        source(c, FakeBackend(), Clock()) as src,
    ):
        src.read()
    messages = {r.getMessage(): r for r in caplog.records}
    assert {"capture_opened", "capture_closed"} <= messages.keys()
    opened = messages["capture_opened"]
    assert opened.consent_id == c.consent_id  # type: ignore[attr-defined]
    assert opened.granted_by == "alice"  # type: ignore[attr-defined]
    assert messages["capture_closed"].frames == 1  # type: ignore[attr-defined]
    assert not any(
        isinstance(v, bytes | bytearray | np.ndarray)
        for r in caplog.records
        for v in vars(r).values()
    )
