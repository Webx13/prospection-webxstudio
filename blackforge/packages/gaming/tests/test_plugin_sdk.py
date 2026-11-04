from __future__ import annotations

import enum
import json
import os
import sys
from pathlib import Path
from typing import Any

import cv2
import pytest

import blackforge_gaming.plugin.loader as loader_module
import blackforge_gaming.plugin.vocab as vocab
from blackforge_gaming.assemble import build_pipeline
from blackforge_gaming.cli import main
from blackforge_gaming.core import Frame, Rect
from blackforge_gaming.plugin import (
    Autonomy,
    PluginRejectedError,
    PolicyDeniedError,
    evaluate_policy,
    load_plugin,
    parse_manifest,
    resolve_autonomy,
)
from tests.onnx_helpers import make_constant_yolo_model
from tests.plugin_helpers import (
    BASE_MANIFEST,
    Mutation,
    codes,
    error_codes,
    make_manifest,
    parse,
    to_json,
    write_plugin,
)
from tests.scenes import blank, fill, paste, sprite

EXAMPLE = Path(__file__).parents[1] / "plugins" / "blackforge-test-game"


# ------------------------------------------------------------------------ plugin d'exemple


def test_the_shipped_example_plugin_is_accepted_and_observes_only() -> None:
    plugin = load_plugin(EXAMPLE)
    manifest = plugin.manifest
    assert plugin.report.accepted and not plugin.report.warnings
    assert (manifest.id, manifest.version) == ("dev.blackforge.test-game", "1.0.0")
    assert manifest.actions == ()  # aucune action : le plugin d'exemple ne contrôle rien
    assert manifest.limits.autonomous_allowed is False


def test_example_plugin_builds_a_working_pipeline_from_data_only() -> None:
    pipeline = build_pipeline(load_plugin(EXAMPLE))
    image = blank(640, 360)
    reds = [Rect(40, 40, 50, 50), Rect(300, 100, 40, 40)]
    greens = [Rect(500, 200, 30, 30)]
    heroes = [paste(image, sprite(), 100, 250), paste(image, sprite(), 400, 30)]
    for r in reds:
        fill(image, r, (0, 0, 255))
    for g in greens:
        fill(image, g, (0, 200, 0))
    result = pipeline.process(Frame(image, 0, 0, "test"))
    by_label: dict[str, list[Any]] = {}
    for d in result.detections:
        by_label.setdefault(d.label, []).append(d.box)
    assert sorted(by_label["enemy"], key=lambda b: b.x) == reds
    assert by_label["ally"] == greens
    assert sorted(by_label["hero"], key=lambda b: b.x) == heroes
    assert not result.degraded


# --------------------------------------------------------------------- manifeste strict


def test_unknown_fields_are_rejected_everywhere() -> None:
    for mutate in (
        lambda d: d.__setitem__("memory_access", True),
        lambda d: d["game"].__setitem__("inject_code", True),
        lambda d: d["limits"].__setitem__("stealth", True),
        lambda d: d["authorization"].__setitem__("bypass_anti_cheat", True),
    ):
        with pytest.raises(PluginRejectedError, match="S003"):
            parse(make_manifest(mutate))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("capture_methods", ["process_memory"]),
        lambda d: d.__setitem__("capture_methods", ["hook_graphics_api"]),
        lambda d: d.__setitem__("actions", [{"type": "inject_input", "max_per_minute": 10}]),
        lambda d: d.__setitem__("permissions", ["memory.read"]),
        lambda d: d.__setitem__("capabilities", ["read_game_memory"]),
        lambda d: d["game"].__setitem__("anti_cheat", "bypassed"),
        lambda d: d["authorization"].__setitem__("kind", "none_needed"),
    ],
)
def test_values_outside_the_closed_vocabulary_are_rejected(mutate: Mutation) -> None:
    with pytest.raises(PluginRejectedError, match="S003"):
        parse(make_manifest(mutate))


def test_vocabularies_never_contain_forbidden_notions() -> None:
    """Garde-fou de régression : personne ne doit pouvoir ajouter au vocabulaire une notion interdite."""
    forbidden = (
        "memory", "inject", "hook", "bypass", "evade", "evasion", "stealth", "cheat", "spoof",
        "exploit", "steal", "credential", "aimbot", "wallhack", "obfuscat", "hide", "undetect",
    )  # fmt: skip
    values = [
        member.value
        for obj in vars(vocab).values()
        if isinstance(obj, type) and issubclass(obj, enum.Enum) and obj is not enum.Enum
        for member in obj
    ]
    assert len(values) > 30  # on a bien trouvé les énumérations
    offenders = [v for v in values if any(term in v.lower() for term in forbidden)]
    assert offenders == []


def test_types_are_strict_not_coerced() -> None:
    with pytest.raises(PluginRejectedError, match="S003"):
        parse(make_manifest(lambda d: d["limits"].__setitem__("max_fps", "30")))
    with pytest.raises(PluginRejectedError, match="S003"):
        parse(make_manifest(lambda d: d["game"].__setitem__("competitive", "false")))
    with pytest.raises(PluginRejectedError, match="S003"):
        parse(make_manifest(lambda d: d["limits"].__setitem__("max_actions_per_minute", 60.5)))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("id", "NotValid"),
        lambda d: d.__setitem__("id", "single"),
        lambda d: d.__setitem__("version", "1.2"),
        lambda d: d.__setitem__("version", "v1.2.3"),
        lambda d: d.__setitem__("capabilities", ["detect_objects", "detect_objects"]),
        lambda d: d["game"].__setitem__("platforms", ["linux", "linux"]),
        lambda d: d.__setitem__(
            "actions",
            [
                {"type": "key_press", "max_per_minute": 5},
                {"type": "key_press", "max_per_minute": 9},
            ],
        ),
        lambda d: d["limits"].__setitem__("max_fps", 120),
        lambda d: d["limits"].__setitem__("max_session_seconds", 10 * 3600),
        lambda d: d.__setitem__("actions", [{"type": "key_press", "max_per_minute": 5000}]),
        lambda d: d.__setitem__("files", {"x.png": "not-a-hash"}),
        lambda d: d["game"].__setitem__("platforms", []),
    ],
)
def test_structural_limits_and_formats_are_enforced(mutate: Mutation) -> None:
    with pytest.raises(PluginRejectedError, match="S003"):
        parse(make_manifest(mutate))


def test_vision_profile_is_validated() -> None:
    def detector(**extra: Any) -> dict[str, Any]:
        return {"kind": "color", "name": "red", "label": "enemy", "hsv_lower": [0, 100, 100],
                "hsv_upper": [10, 255, 255], **extra}  # fmt: skip

    for bad in (
        {"detectors": [detector(hsv_upper=[200, 255, 255])]},
        {"detectors": [detector(), detector()]},
        {"detectors": [detector(roi="nowhere")]},
        {"regions": [{"name": "r", "x": 0.6, "y": 0, "w": 0.6, "h": 1}], "detectors": []},
        {"detectors": [{"kind": "shell", "name": "x", "label": "x", "command": "rm -rf /"}]},
    ):
        with pytest.raises(PluginRejectedError, match="S003"):
            parse(make_manifest(_vision(bad)))


# ------------------------------------------------------------------ politique : refus


def _g(**kw: Any) -> Mutation:
    return lambda d: d["game"].update(kw)


def _auth(kind: str, evidence: str | None = None) -> Mutation:
    return lambda d: d["authorization"].update({"kind": kind, "evidence": evidence})


def _vision(update: dict[str, Any]) -> Mutation:
    return lambda d: d["vision"].update(update)


def _files(files: dict[str, str]) -> Mutation:
    return lambda d: d.update(files=files)


def _limits(**kw: Any) -> Mutation:
    return lambda d: d["limits"].update(kw)


REJECTIONS: list[tuple[str, list[Mutation], str]] = [
    (
        "P001 autorisation incompatible avec le mode",
        [_auth("publisher_permission", "https://x.example/ok")],
        "P001",
    ),
    (
        "P002 preuve requise (serveur privé)",
        [_g(mode="private_server"), _auth("private_server_operator")],
        "P002",
    ),
    (
        "P002 preuve requise (permission éditeur)",
        [_g(mode="single_player"), _auth("publisher_permission", "  ")],
        "P002",
    ),
    (
        "P003 multijoueur en ligne sans permission éditeur",
        [_g(mode="online_multiplayer"), _auth("own_game")],
        "P003",
    ),
    ("P004 compétitif sans permission éditeur", [_g(competitive=True), _auth("own_game")], "P004"),
    (
        "P005 compétitif en autonome",
        [_g(competitive=True), _limits(autonomous_allowed=True)],
        "P005",
    ),
    ("P006 anti-cheat présent sans permission éditeur", [_g(anti_cheat="present")], "P006"),
    ("P006 anti-cheat inconnu = présent", [_g(anti_cheat="unknown")], "P006"),
    (
        "P007 anti-cheat + autonome",
        [
            _g(anti_cheat="present", mode="single_player"),
            _auth("publisher_permission", "https://x.example/ok"),
            _limits(autonomous_allowed=True),
        ],
        "P007",
    ),
    (
        "P008 action sans permission",
        [lambda d: d.update(actions=[{"type": "mouse_click", "max_per_minute": 10}])],
        "P008",
    ),
    ("P008 capture sans permission", [lambda d: d.update(permissions=[])], "P008"),
    (
        "P009 canal de test hors jeu de test",
        [
            _g(mode="private_server"),
            _auth("private_server_operator", "je suis l'opérateur"),
            lambda d: d.update(actions=[{"type": "test_harness_command", "max_per_minute": 5}]),
        ],
        "P009",
    ),
    (
        "P010 débit d'action > limite globale",
        [
            lambda d: d.update(
                actions=[{"type": "key_press", "max_per_minute": 100}],
                permissions=["capture.screen", "input.keyboard"],
            )
        ],
        "P010",
    ),
    ("P011 autonomie par défaut incohérente", [_limits(default_autonomy="autonomous")], "P011"),
    (
        "P012 détecteur sans capacité de vision",
        [
            lambda d: d.update(
                capabilities=[],
                vision={
                    "detectors": [
                        {
                            "kind": "color",
                            "name": "r",
                            "label": "x",
                            "hsv_lower": [0, 1, 1],
                            "hsv_upper": [5, 255, 255],
                        }
                    ]
                },
            )
        ],
        "P012",
    ),
    (
        "P013 fichier référencé non scellé",
        [
            lambda d: d["vision"].update(
                detectors=[{"kind": "template", "name": "t", "label": "x", "template": "t.png"}]
            )
        ],
        "P013",
    ),
    (
        "P014 fichier scellé jamais référencé",
        [lambda d: d.update(files={"orphelin.png": "0" * 64})],
        "P014",
    ),
]


@pytest.mark.parametrize(("label", "mutations", "code"), REJECTIONS, ids=[r[0] for r in REJECTIONS])
def test_policy_rejects_non_compliant_manifests(
    label: str, mutations: list[Mutation], code: str
) -> None:
    data = make_manifest(*mutations)
    assert code in error_codes(data), label
    assert not evaluate_policy(parse(data)).accepted


# -------------------------------------------------------------- politique : acceptation


ACCEPTANCES: list[tuple[str, list[Mutation]]] = [
    ("jeu de l'utilisateur", []),
    ("environnement de test", [_g(mode="test_environment"), _auth("test_environment")]),
    ("solo hors ligne", [_g(mode="single_player"), _auth("offline_single_player")]),
    (
        "serveur privé avec preuve",
        [
            _g(mode="private_server"),
            _auth("private_server_operator", "j'opère ce serveur : https://srv.example"),
        ],
    ),
    (
        "multijoueur : CGU autorisant l'automatisation, avec preuve",
        [
            _g(mode="online_multiplayer"),
            _auth("terms_permit_automation", "https://jeu.example/tos#automation"),
        ],
    ),
    (
        "anti-cheat : permission éditeur + preuve, supervisé",
        [
            _g(mode="single_player", anti_cheat="present"),
            _auth("publisher_permission", "courriel de l'éditeur, réf. 2026-114"),
        ],
    ),
    (
        "compétitif : permission éditeur + preuve, supervisé",
        [
            _g(mode="online_multiplayer", competitive=True),
            _auth("publisher_permission", "contrat n° 42"),
        ],
    ),
    (
        "saisie clavier déclarée et permise",
        [
            lambda d: d.update(
                actions=[{"type": "key_press", "max_per_minute": 30}],
                permissions=["capture.screen", "input.keyboard"],
            )
        ],
    ),
    (
        "canal de test dans un jeu de test",
        [
            _g(mode="test_environment"),
            _auth("test_environment"),
            lambda d: d.update(actions=[{"type": "test_harness_command", "max_per_minute": 5}]),
        ],
    ),
    (
        "mode autonome sur un jeu de l'utilisateur",
        [_limits(autonomous_allowed=True, default_autonomy="autonomous")],
    ),
]


@pytest.mark.parametrize(("label", "mutations"), ACCEPTANCES, ids=[a[0] for a in ACCEPTANCES])
def test_policy_accepts_legitimate_manifests(label: str, mutations: list[Mutation]) -> None:
    report = evaluate_policy(parse(make_manifest(*mutations)))
    assert report.accepted, f"{label}: {[(v.code, v.message) for v in report.errors]}"


def test_warnings_flag_unsupported_or_excess_declarations() -> None:
    data = make_manifest(
        lambda d: d.update(
            capabilities=["detect_objects", "read_text", "track_objects"],
            permissions=["capture.screen", "storage.recordings"],
            actions=[{"type": "key_press", "max_per_minute": 5}],
        ),
        lambda d: d["permissions"].append("input.keyboard"),
        _limits(autonomous_allowed=True),
    )
    report = evaluate_policy(parse(data))
    assert report.accepted  # des avertissements ne bloquent pas
    assert {"W001", "W002", "W003"} <= {w.code for w in report.warnings}
    assert sum(1 for w in report.warnings if w.code == "W001") == 2  # read_text et track_objects


def test_a_clean_observation_only_manifest_has_no_violations() -> None:
    assert codes(make_manifest()) == set()


# ---------------------------------------------------------------- autonomie par projet


def test_autonomy_defaults_and_denial_are_explicit() -> None:
    supervised = parse(make_manifest())
    assert resolve_autonomy(supervised) is Autonomy.SUPERVISED
    assert resolve_autonomy(supervised, Autonomy.SUPERVISED) is Autonomy.SUPERVISED
    with pytest.raises(PolicyDeniedError, match="autonome"):
        resolve_autonomy(supervised, Autonomy.AUTONOMOUS)  # jamais de dégradation silencieuse

    permissive = parse(make_manifest(_limits(autonomous_allowed=True)))
    assert resolve_autonomy(permissive, Autonomy.AUTONOMOUS) is Autonomy.AUTONOMOUS
    assert (
        resolve_autonomy(permissive) is Autonomy.SUPERVISED
    )  # le défaut du plugin reste supervisé
    assert (
        resolve_autonomy(permissive, Autonomy.SUPERVISED) is Autonomy.SUPERVISED
    )  # le projet peut être plus strict

    autonomous_default = parse(
        make_manifest(_limits(autonomous_allowed=True, default_autonomy="autonomous"))
    )
    assert resolve_autonomy(autonomous_default) is Autonomy.AUTONOMOUS


# ------------------------------------------------------------------------------ chargeur


def valid_template_png() -> bytes:
    ok, encoded = cv2.imencode(".png", sprite())
    assert ok
    return bytes(encoded.tobytes())


def template_manifest() -> dict[str, Any]:
    return make_manifest(
        lambda d: d["vision"].update(
            detectors=[
                {
                    "kind": "template",
                    "name": "hero",
                    "label": "hero",
                    "template": "t/hero.png",
                    "threshold": 0.9,
                }
            ]
        )
    )


def test_loader_accepts_a_sealed_plugin_and_builds_a_pipeline(tmp_path: Path) -> None:
    root = write_plugin(tmp_path / "p", template_manifest(), {"t/hero.png": valid_template_png()})
    plugin = load_plugin(root)
    image = blank()
    box = paste(image, sprite(), 50, 60)
    result = build_pipeline(plugin).process(Frame(image, 0, 0, "t"))
    assert [d.box for d in result.detections] == [box]


def test_loader_rejects_tampered_and_missing_files(tmp_path: Path) -> None:
    root = write_plugin(tmp_path / "p", template_manifest(), {"t/hero.png": valid_template_png()})
    (root / "t" / "hero.png").write_bytes(valid_template_png() + b"x")
    with pytest.raises(PluginRejectedError, match="S008"):
        load_plugin(root)
    (root / "t" / "hero.png").unlink()
    with pytest.raises(PluginRejectedError, match="S006"):
        load_plugin(root)


def test_loader_rejects_unsealed_references_before_touching_files(tmp_path: Path) -> None:
    root = write_plugin(
        tmp_path / "p", template_manifest(), {"t/hero.png": valid_template_png()}, seal=False
    )
    with pytest.raises(PluginRejectedError, match="P013"):
        load_plugin(root)


def test_loader_confines_files_to_the_plugin_directory(tmp_path: Path) -> None:
    secret = tmp_path / "secret.png"
    secret.write_bytes(valid_template_png())
    sealed_hash = __import__("hashlib").sha256(valid_template_png()).hexdigest()
    for bad_path in ("../secret.png", "/etc/hostname", "a/../../secret.png"):
        data = make_manifest(
            _vision(
                {
                    "detectors": [
                        {"kind": "template", "name": "t", "label": "x", "template": bad_path}
                    ]
                }
            ),
            _files({bad_path: sealed_hash}),
        )
        root = write_plugin(tmp_path / "plug", data, seal=False)
        with pytest.raises(PluginRejectedError, match="S005"):
            load_plugin(root)


def test_loader_rejects_parent_segments_even_when_they_stay_inside_the_plugin(
    tmp_path: Path,
) -> None:
    """Première couche de défense : tout « .. » est refusé, même si le chemin résolu reste dans le dossier."""
    sealed = __import__("hashlib").sha256(valid_template_png()).hexdigest()
    path = "t/../t/hero.png"
    data = make_manifest(
        _vision({"detectors": [{"kind": "template", "name": "t", "label": "x", "template": path}]}),
        _files({path: sealed}),
    )
    root = write_plugin(tmp_path / "p", data, {"t/hero.png": valid_template_png()}, seal=False)
    with pytest.raises(PluginRejectedError, match="S005"):
        load_plugin(root)


@pytest.mark.skipif(
    sys.platform == "win32", reason="liens symboliques : droits spécifiques sous Windows"
)
def test_loader_rejects_a_symlink_escaping_the_plugin_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(valid_template_png())
    root = write_plugin(tmp_path / "p", template_manifest(), {"t/hero.png": valid_template_png()})
    (root / "t" / "hero.png").unlink()
    os.symlink(
        outside, root / "t" / "hero.png"
    )  # même contenu, donc même empreinte : seul le confinement protège
    with pytest.raises(PluginRejectedError, match="S005"):
        load_plugin(root)


def test_loader_enforces_size_limits_and_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = write_plugin(tmp_path / "p", template_manifest(), {"t/hero.png": valid_template_png()})
    monkeypatch.setattr(loader_module, "MAX_FILE_BYTES", 10)
    with pytest.raises(PluginRejectedError, match="S007"):
        load_plugin(root)
    monkeypatch.undo()

    with pytest.raises(PluginRejectedError, match="S001"):
        parse_manifest(b" " * (loader_module.MAX_MANIFEST_BYTES + 1))
    with pytest.raises(PluginRejectedError, match="S002"):
        parse_manifest(b"{ pas du json")
    with pytest.raises(PluginRejectedError, match="S002"):
        parse_manifest(b"\xff\xfe\x00")
    with pytest.raises(PluginRejectedError, match="S004"):
        load_plugin(tmp_path / "vide")


def test_loading_a_plugin_never_executes_its_code(tmp_path: Path) -> None:
    """Un plugin est de la donnée : un fichier .py qu'il contient n'est ni importé ni exécuté."""
    marker = tmp_path / "EXECUTED"
    root = write_plugin(tmp_path / "p", make_manifest())
    (root / "evil.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('boom')\n"
    )
    (root / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('boom')\n"
    )
    plugin = load_plugin(root)
    build_pipeline(plugin)
    assert plugin.report.accepted
    assert not marker.exists()
    assert "evil" not in sys.modules


def test_a_rejected_plugin_reports_every_violation(tmp_path: Path) -> None:
    data = make_manifest(
        _g(anti_cheat="present", competitive=True), lambda d: d.update(permissions=[])
    )
    root = write_plugin(tmp_path / "p", data)
    with pytest.raises(PluginRejectedError) as raised:
        load_plugin(root)
    assert {"P004", "P006", "P008"} <= {v.code for v in raised.value.violations}
    assert "dev.example.my-game" in str(raised.value)


# --------------------------------------------------------------- détecteur ONNX scellé


def test_onnx_detector_declared_in_a_plugin_is_sealed_and_assembled(tmp_path: Path) -> None:
    model = tmp_path / "m.onnx"
    make_constant_yolo_model(model)
    data = make_manifest(
        lambda d: d["vision"].update(
            detectors=[
                {
                    "kind": "onnx",
                    "name": "yolo",
                    "label": "model",
                    "model": "models/m.onnx",
                    "labels": ["enemy", "ally"],
                }
            ]
        )
    )
    root = write_plugin(tmp_path / "p", data, {"models/m.onnx": model.read_bytes()})
    plugin = load_plugin(root)
    result = build_pipeline(plugin).process(Frame(blank(128, 64), 0, 0, "t"))
    assert sorted(d.label for d in result.detections) == ["ally", "enemy", "enemy"]
    (root / "models" / "m.onnx").write_bytes(model.read_bytes() + b"\x00")  # modèle altéré
    with pytest.raises(PluginRejectedError, match="S008"):
        load_plugin(root)


def test_a_sealed_but_undecodable_template_fails_cleanly(tmp_path: Path) -> None:
    root = write_plugin(
        tmp_path / "p", template_manifest(), {"t/hero.png": b"ceci n'est pas un PNG"}
    )
    plugin = load_plugin(root)  # l'intégrité est correcte...
    with pytest.raises(ValueError, match="illisible"):  # ...mais le contenu est inutilisable
        build_pipeline(plugin)


# ------------------------------------------------------------------------------- CLI


def test_cli_plugin_validate_accepts_and_rejects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plugin", "validate", str(EXAMPLE)]) == 0
    assert "ACCEPTÉ" in capsys.readouterr().out

    assert main(["plugin", "validate", str(EXAMPLE), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["accepted"] is True

    bad = write_plugin(tmp_path / "bad", make_manifest(_g(anti_cheat="present")))
    assert main(["plugin", "validate", str(bad)]) == 1
    assert "[P006]" in capsys.readouterr().err

    assert main(["plugin", "validate", str(bad), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["accepted"] is False and report["errors"][0]["code"] == "P006"


def test_base_manifest_fixture_is_itself_valid() -> None:  # garde-fou des tests eux-mêmes
    assert error_codes(BASE_MANIFEST) == set()
    assert to_json(BASE_MANIFEST).startswith(b"{")
