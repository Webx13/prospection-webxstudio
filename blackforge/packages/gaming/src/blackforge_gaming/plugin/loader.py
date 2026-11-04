"""Chargement sûr d'un plugin depuis un dossier.

Un plugin est de la DONNÉE : ``plugin.json`` + fichiers référencés (gabarits PNG, modèles ONNX).
Charger un plugin n'exécute aucun code tiers. Garanties vérifiées par les tests :

* manifeste de taille bornée, JSON valide, structure stricte (champ inconnu = refus) ;
* politique de conformité évaluée avant toute utilisation (refus = ``PluginRejectedError``) ;
* chaque fichier référencé : confiné au dossier du plugin (pas de ``..``, de chemin absolu ni de lien
  symbolique sortant), fichier régulier, de taille bornée, empreinte SHA-256 identique à la déclaration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from blackforge_gaming.plugin.manifest import PluginManifest
from blackforge_gaming.plugin.policy import PolicyReport, PolicyViolation, evaluate_policy

MANIFEST_NAME: Final = "plugin.json"
MAX_MANIFEST_BYTES: Final = 256 * 1024
MAX_FILE_BYTES: Final = 512 * 1024 * 1024


class PluginRejectedError(Exception):
    """Plugin invalide, non conforme ou altéré. ``violations`` détaille chaque motif."""

    def __init__(self, plugin: str, violations: tuple[PolicyViolation, ...]) -> None:
        self.plugin = plugin
        self.violations = violations
        detail = "; ".join(f"[{v.code}] {v.message}" for v in violations)
        super().__init__(f"plugin « {plugin} » refusé : {detail}")


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    manifest: PluginManifest
    root: Path
    report: PolicyReport

    def resolve(self, relative: str) -> Path:
        """Chemin absolu d'un fichier DÉJÀ vérifié (confinement + empreinte) au chargement."""
        return _confined(self.root, relative)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _confined(root: Path, relative: str) -> Path:
    """Résout ``relative`` sous ``root`` ; lève ``ValueError`` si le résultat sort du dossier."""
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        msg = f"chemin non autorisé : {relative!r}"
        raise ValueError(msg)
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()):
        msg = f"le chemin {relative!r} sort du dossier du plugin"
        raise ValueError(msg)
    return resolved


def _reject(plugin: str, code: str, message: str) -> PluginRejectedError:
    return PluginRejectedError(plugin, (PolicyViolation(code, "error", message),))


def parse_manifest(raw: bytes, *, source: str = "plugin.json") -> PluginManifest:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise _reject(source, "S001", f"manifeste trop volumineux (> {MAX_MANIFEST_BYTES} octets)")
    try:
        json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _reject(source, "S002", f"JSON invalide : {exc}") from exc
    try:
        return PluginManifest.model_validate_json(raw)
    except ValidationError as exc:
        violations = tuple(
            PolicyViolation(
                "S003",
                "error",
                f"{'.'.join(str(p) for p in err['loc']) or '(racine)'} : {err['msg']}",
            )
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise PluginRejectedError(source, violations) from exc


def load_plugin(directory: Path) -> LoadedPlugin:
    """Charge, valide, évalue la conformité et vérifie l'intégrité. Sinon ``PluginRejectedError``."""
    root = directory.resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise _reject(str(directory), "S004", f"{MANIFEST_NAME} introuvable dans {directory}")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise _reject(
            str(directory), "S001", f"manifeste trop volumineux (> {MAX_MANIFEST_BYTES} octets)"
        )
    manifest = parse_manifest(manifest_path.read_bytes(), source=str(directory))

    report = evaluate_policy(manifest)
    if not report.accepted:
        raise PluginRejectedError(manifest.id, report.errors)

    problems: list[PolicyViolation] = []
    for relative, expected in manifest.files.items():
        try:
            path = _confined(root, relative)
        except ValueError as exc:
            problems.append(PolicyViolation("S005", "error", str(exc)))
            continue
        if not path.is_file():
            problems.append(PolicyViolation("S006", "error", f"fichier introuvable : {relative!r}"))
        elif path.stat().st_size > MAX_FILE_BYTES:
            problems.append(
                PolicyViolation("S007", "error", f"fichier trop volumineux : {relative!r}")
            )
        elif sha256_file(path) != expected:
            problems.append(
                PolicyViolation(
                    "S008",
                    "error",
                    f"empreinte SHA-256 différente pour {relative!r} (fichier altéré ?)",
                )
            )
    if problems:
        raise PluginRejectedError(manifest.id, tuple(problems))
    return LoadedPlugin(manifest=manifest, root=root, report=report)
