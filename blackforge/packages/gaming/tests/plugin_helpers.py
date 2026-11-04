"""Aides pour fabriquer des plugins de test (manifestes en dict, dossiers scellés)."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from blackforge_gaming.plugin import PluginManifest, evaluate_policy, parse_manifest

Mutation = Callable[[dict[str, Any]], None]

BASE_MANIFEST: dict[str, Any] = {
    "manifest_version": 1,
    "id": "dev.example.my-game",
    "name": "Mon jeu",
    "version": "1.2.3",
    "publisher": "Alice",
    "description": "Plugin de test.",
    "game": {
        "title": "Mon jeu",
        "platforms": ["macos", "linux"],
        "mode": "user_developed",
        "competitive": False,
        "anti_cheat": "none",
    },
    "authorization": {"kind": "own_game", "evidence": None},
    "capabilities": ["detect_objects"],
    "apis": [],
    "capture_methods": ["display"],
    "actions": [],
    "permissions": ["capture.screen"],
    "limits": {
        "max_session_seconds": 600,
        "max_fps": 30,
        "max_actions_per_minute": 60,
        "autonomous_allowed": False,
        "default_autonomy": "supervised",
    },
    "vision": {"regions": [], "detectors": [], "change_threshold": 0.002, "max_stale_frames": 30},
    "files": {},
}


def make_manifest(*mutations: Mutation) -> dict[str, Any]:
    data = copy.deepcopy(BASE_MANIFEST)
    for mutate in mutations:
        mutate(data)
    return data


def to_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data).encode()


def parse(data: dict[str, Any]) -> PluginManifest:
    return parse_manifest(to_json(data))


def codes(data: dict[str, Any]) -> set[str]:
    """Codes de politique (erreurs + avertissements) d'un manifeste structurellement valide."""
    return {v.code for v in evaluate_policy(parse(data)).violations}


def error_codes(data: dict[str, Any]) -> set[str]:
    return {v.code for v in evaluate_policy(parse(data)).errors}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_plugin(
    root: Path,
    data: dict[str, Any],
    files: dict[str, bytes] | None = None,
    *,
    seal: bool = True,
) -> Path:
    """Écrit ``plugin.json`` + fichiers ; scelle automatiquement les empreintes sauf si ``seal=False``."""
    root.mkdir(parents=True, exist_ok=True)
    files = files or {}
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    if seal:
        data = copy.deepcopy(data)
        data["files"] = {rel: sha256_bytes(content) for rel, content in files.items()}
    (root / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    return root
