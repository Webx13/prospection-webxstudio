from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Self

import numpy as np
import pytest

import blackforge_gaming
from blackforge_gaming.capture import CaptureUnavailableError, ReplaySource, record_frames
from blackforge_gaming.cli import main
from blackforge_gaming.core import EmergencyStop, Frame, FrameSource, KillSwitch
from tests.scenes import blank, fill

# ---------------------------------------------------------------------- source en mémoire


class ListSource:
    """FrameSource minimale : prouve que le protocole suffit à brancher n'importe quelle source."""

    source_id = "memory"

    def __init__(self, frames: list[Frame]) -> None:
        self._frames: Iterator[Frame] = iter(frames)

    def open(self) -> None: ...

    def read(self) -> Frame | None:
        return next(self._frames, None)

    def close(self) -> None: ...

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


def sample_frames(count: int = 4) -> list[Frame]:
    frames = []
    for i in range(count):
        image = blank(64, 48)
        image[i * 5 : i * 5 + 6, 10:20] = (200, 100, 50)  # contenu différent à chaque image
        frames.append(
            Frame(
                image,
                index=i,
                captured_at_ns=5_000_000_000 + i * 40_000_000,
                source_id="memory",
                pixel_scale=2.0,
                origin=(7, 9),
            )
        )
    return frames


# ------------------------------------------------------------------------------- rejeu


def test_record_then_replay_is_pixel_exact_and_keeps_metadata(tmp_path: Path) -> None:
    originals = sample_frames()
    source = ListSource(originals)
    assert isinstance(source, FrameSource)
    assert record_frames(source, tmp_path / "rec", max_frames=10) == 4

    with ReplaySource(tmp_path / "rec") as replay:
        assert len(replay) == 4
        replayed = []
        while (frame := replay.read()) is not None:
            replayed.append(frame)
    assert len(replayed) == 4
    for original, again in zip(originals, replayed, strict=True):
        assert np.array_equal(original.image, again.image)  # PNG sans perte
        assert again.index == original.index
        assert (again.pixel_scale, again.origin) == (2.0, (7, 9))
        assert again.captured_at_ns == original.captured_at_ns - originals[0].captured_at_ns
    assert replayed[0].source_id == "replay:rec"
    assert replayed[0].consent_id is None


def test_record_honours_max_frames_and_validates(tmp_path: Path) -> None:
    assert record_frames(ListSource(sample_frames(4)), tmp_path / "a", max_frames=2) == 2
    manifest = json.loads((tmp_path / "a" / "manifest.json").read_text())
    assert len(manifest["frames"]) == 2 and manifest["version"] == 1
    with pytest.raises(ValueError, match="max_frames"):
        record_frames(ListSource([]), tmp_path / "b", max_frames=0)


def test_replay_can_loop_and_is_restartable(tmp_path: Path) -> None:
    record_frames(ListSource(sample_frames(2)), tmp_path / "r", max_frames=2)
    with ReplaySource(tmp_path / "r", loop=True) as replay:
        indexes = [replay.read().index for _ in range(5)]  # type: ignore[union-attr]
    assert indexes == [0, 1, 2, 3, 4]  # l'index croît, même quand on reboucle


def test_replay_without_manifest_uses_a_virtual_clock(tmp_path: Path) -> None:
    import cv2

    for i in range(3):
        cv2.imwrite(str(tmp_path / f"{i}.png"), blank(32, 32))
    with ReplaySource(tmp_path, fps=10.0) as replay:
        stamps = [replay.read().captured_at_ns for _ in range(3)]  # type: ignore[union-attr]
    assert stamps == [0, 100_000_000, 200_000_000]


def test_replay_errors_are_explicit(tmp_path: Path) -> None:
    with pytest.raises(CaptureUnavailableError, match="introuvable"):
        ReplaySource(tmp_path / "absent").open()
    (tmp_path / "empty").mkdir()
    with pytest.raises(CaptureUnavailableError, match="aucune image"):
        ReplaySource(tmp_path / "empty").open()
    with pytest.raises(ValueError, match="fps"):
        ReplaySource(tmp_path, fps=0)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps({"version": 99, "frames": [{"file": "x.png"}]}))
    with pytest.raises(CaptureUnavailableError, match="version"):
        ReplaySource(bad).open()
    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "0.png").write_bytes(b"pas une image")
    with ReplaySource(corrupt) as replay, pytest.raises(CaptureUnavailableError, match="illisible"):
        replay.read()


def test_replay_honours_the_kill_switch(tmp_path: Path) -> None:
    record_frames(ListSource(sample_frames(2)), tmp_path / "r", max_frames=2)
    kill = KillSwitch()
    with ReplaySource(tmp_path / "r", kill_switch=kill) as replay:
        assert replay.read() is not None
        kill.trigger("stop")
        with pytest.raises(EmergencyStop):
            replay.read()


# ------------------------------------------------------------ frontières d'architecture

PACKAGE_ROOT = Path(blackforge_gaming.__file__).parent

# Qui peut importer quoi À L'INTÉRIEUR du paquet. Les moteurs ne se connaissent pas entre eux :
# ils ne partagent que `core` (contrats) — ce qui les rend remplaçables indépendamment.
ALLOWED_INTERNAL = {
    "core": set(),
    "consent": {"core"},
    "capture": {"core", "consent"},
    "vision": {"core"},
    "perception": {"core"},
}
# Dépendances tierces autorisées par moteur (le cœur et la perception restent légers).
FORBIDDEN_THIRD_PARTY = {
    "core": {"cv2", "mss", "onnxruntime", "onnx", "pydantic"},
    "perception": {"cv2", "mss", "onnxruntime", "onnx"},
    "consent": {"cv2", "mss", "onnxruntime", "onnx"},
    "vision": {"mss"},
    "capture": {"onnxruntime", "onnx"},
}
# Racine de composition : seule à pouvoir tout assembler.
COMPOSITION_ROOT = {"probe.py", "cli.py", "__init__.py"}


def imports_of(path: Path) -> Iterator[str]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # les imports relatifs sont interdits : ils masquent les frontières
                yield f"<relative:{'.' * node.level}{node.module or ''}>"
            elif node.module:
                yield node.module


@pytest.mark.parametrize("engine", sorted(ALLOWED_INTERNAL))
def test_engine_only_depends_on_allowed_siblings_and_libraries(engine: str) -> None:
    violations = []
    for path in sorted((PACKAGE_ROOT / engine).rglob("*.py")):
        for module in imports_of(path):
            where = path.relative_to(PACKAGE_ROOT)
            if module.startswith("<relative:"):
                violations.append(f"{where}: import relatif interdit ({module})")
            elif module.startswith("blackforge_gaming."):
                target = module.split(".")[1]
                if target != engine and target not in ALLOWED_INTERNAL[engine]:
                    violations.append(f"{where}: {engine} ne doit pas dépendre de {target}")
            elif module.split(".")[0] in FORBIDDEN_THIRD_PARTY[engine]:
                violations.append(f"{where}: dépendance interdite {module}")
    assert not violations, "\n".join(violations)


def test_every_module_directory_is_covered_by_the_rules() -> None:
    engines = {p.name for p in PACKAGE_ROOT.iterdir() if p.is_dir() and not p.name.startswith("_")}
    assert engines == set(ALLOWED_INTERNAL), "un nouveau moteur doit déclarer ses frontières"


def test_no_stray_module_outside_engines_except_the_composition_root() -> None:
    top_level = {p.name for p in PACKAGE_ROOT.glob("*.py")}
    assert top_level <= COMPOSITION_ROOT


def test_importing_core_does_not_pull_heavy_libraries() -> None:
    import subprocess
    import sys

    code = (
        "import sys, blackforge_gaming.core, blackforge_gaming.perception;"
        "heavy={'cv2','mss','onnxruntime','onnx'} & set(sys.modules);"
        "print(sorted(heavy))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


# ------------------------------------------------------------------------------- CLI


def test_probe_json_reports_real_capabilities(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["probe", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert {"platform", "machine", "python", "capabilities"} <= report.keys()
    names = {c["name"] for c in report["capabilities"]}
    assert {
        "capture.screen",
        "capture.macos_screen_recording",
        "vision.opencv",
        "vision.onnxruntime",
    } <= names
    assert all(
        c["availability"] in {"available", "unavailable", "unknown", "not_applicable"}
        for c in report["capabilities"]
    )
    opencv = next(c for c in report["capabilities"] if c["name"] == "vision.opencv")
    assert opencv["availability"] == "available" and opencv["detail"]


def test_selfcheck_refuses_to_capture_without_explicit_consent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["selfcheck-capture"]) == 2
    assert "--i-consent" in capsys.readouterr().err


def test_selfcheck_reports_failure_cleanly_without_a_display(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    if __import__("sys").platform != "linux":
        pytest.skip("le cas « pas d'affichage » est propre à Linux")
    assert main(["selfcheck-capture", "--i-consent"]) == 1
    assert "ÉCHEC" in capsys.readouterr().err


def test_selfcheck_rejects_a_malformed_region() -> None:
    with pytest.raises(SystemExit):
        main(["selfcheck-capture", "--i-consent", "--region", "10,10,0,5"])


def test_fill_helper_sanity() -> None:  # garde-fou : les scènes de test sont bien ce qu'on croit
    image = blank(20, 20)
    from blackforge_gaming.core import Rect

    fill(image, Rect(2, 2, 4, 4), (1, 2, 3))
    assert tuple(image[3, 3]) == (1, 2, 3) and tuple(image[0, 0]) != (1, 2, 3)
