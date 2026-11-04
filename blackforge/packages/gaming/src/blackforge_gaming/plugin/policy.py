"""Politique de conformité appliquée à tout manifeste, AVANT qu'un plugin puisse être utilisé.

Chaque règle a un code stable (``P0xx`` = refus, ``W0xx`` = avertissement).

Limite assumée : les champs d'autorisation sont DÉCLARATIFS. BLACKFORGE ne peut pas vérifier qu'un
éditeur a réellement donné sa permission ni qu'un jeu n'a pas d'anti-cheat : la politique impose que
la déclaration soit explicite, cohérente et auditée, pas qu'elle soit vraie. La responsabilité d'usage
reste à l'utilisateur ; un futur registre de plugins revu humainement renforcera ce contrôle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from blackforge_gaming.plugin.manifest import PluginManifest
from blackforge_gaming.plugin.vocab import (
    ACTION_PERMISSION,
    CAPTURE_PERMISSION,
    INPUT_ACTIONS,
    SUPPORTED_CAPABILITIES,
    ActionType,
    AntiCheat,
    AuthorizationKind,
    Autonomy,
    GameMode,
)

Severity = Literal["error", "warning"]

# Plafonds du SDK : un plugin ne peut pas demander plus, quoi qu'il déclare.
SDK_MAX_ACTIONS_PER_MINUTE: Final = 300
SDK_MAX_FPS: Final = 60.0
SDK_MAX_SESSION_SECONDS: Final = 4 * 3600

_THIRD_PARTY_KINDS = frozenset(
    {
        AuthorizationKind.PUBLISHER_PERMISSION,
        AuthorizationKind.TERMS_PERMIT_AUTOMATION,
        AuthorizationKind.PRIVATE_SERVER_OPERATOR,
    }
)
_PERMISSION_FROM_PUBLISHER = frozenset(
    {AuthorizationKind.PUBLISHER_PERMISSION, AuthorizationKind.TERMS_PERMIT_AUTOMATION}
)
_ALLOWED_AUTHORIZATION: dict[GameMode, frozenset[AuthorizationKind]] = {
    GameMode.SINGLE_PLAYER: frozenset(
        {
            AuthorizationKind.OWN_GAME,
            AuthorizationKind.OFFLINE_SINGLE_PLAYER,
            AuthorizationKind.PUBLISHER_PERMISSION,
            AuthorizationKind.TERMS_PERMIT_AUTOMATION,
        }
    ),
    GameMode.TEST_ENVIRONMENT: frozenset(
        {AuthorizationKind.TEST_ENVIRONMENT, AuthorizationKind.OWN_GAME}
    ),
    GameMode.USER_DEVELOPED: frozenset({AuthorizationKind.OWN_GAME}),
    GameMode.PRIVATE_SERVER: frozenset(
        {
            AuthorizationKind.PRIVATE_SERVER_OPERATOR,
            AuthorizationKind.PUBLISHER_PERMISSION,
            AuthorizationKind.TERMS_PERMIT_AUTOMATION,
        }
    ),
    GameMode.ONLINE_MULTIPLAYER: _PERMISSION_FROM_PUBLISHER,
}


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    code: str
    severity: Severity
    message: str


@dataclass(frozen=True, slots=True)
class PolicyReport:
    plugin_id: str
    violations: tuple[PolicyViolation, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[PolicyViolation, ...]:
        return tuple(v for v in self.violations if v.severity == "error")

    @property
    def warnings(self) -> tuple[PolicyViolation, ...]:
        return tuple(v for v in self.violations if v.severity == "warning")

    @property
    def accepted(self) -> bool:
        return not self.errors


class PolicyDeniedError(PermissionError):
    """Une opération demandée dépasse ce que le manifeste et la politique autorisent."""


def evaluate_policy(manifest: PluginManifest) -> PolicyReport:
    found: list[PolicyViolation] = []

    def error(code: str, message: str) -> None:
        found.append(PolicyViolation(code, "error", message))

    def warning(code: str, message: str) -> None:
        found.append(PolicyViolation(code, "warning", message))

    game, auth, limits = manifest.game, manifest.authorization, manifest.limits
    has_evidence = bool(auth.evidence and auth.evidence.strip())
    input_actions = [a for a in manifest.actions if a.type in INPUT_ACTIONS]

    # P001 — autorisation cohérente avec le mode de jeu
    if auth.kind not in _ALLOWED_AUTHORIZATION[game.mode]:
        allowed = ", ".join(sorted(k.value for k in _ALLOWED_AUTHORIZATION[game.mode]))
        error(
            "P001",
            f"autorisation « {auth.kind.value} » incompatible avec le mode « {game.mode.value} » "
            f"(autorisations acceptées : {allowed})",
        )
    # P002 — preuve requise quand l'autorisation dépend d'un tiers
    if auth.kind in _THIRD_PARTY_KINDS and not has_evidence:
        error(
            "P002",
            f"l'autorisation « {auth.kind.value} » exige une preuve (URL, référence de licence…)",
        )
    # P003 — multijoueur en ligne : permission de l'éditeur ou CGU explicites, rien d'autre
    if game.mode is GameMode.ONLINE_MULTIPLAYER and auth.kind not in _PERMISSION_FROM_PUBLISHER:
        error(
            "P003",
            "jeu multijoueur en ligne : seule une permission de l'éditeur ou des CGU autorisant "
            "explicitement l'automatisation est acceptée",
        )
    # P004 — compétitif : permission de l'éditeur ET jamais d'autonomie
    if game.competitive:
        if auth.kind is not AuthorizationKind.PUBLISHER_PERMISSION:
            error(
                "P004",
                "jeu compétitif : exige une permission explicite de l'éditeur (publisher_permission)",
            )
        if limits.autonomous_allowed or limits.default_autonomy is Autonomy.AUTONOMOUS:
            error("P005", "jeu compétitif : le mode autonome est interdit (supervisé uniquement)")
    # P006 — anti-cheat présent ou inconnu : permission de l'éditeur, jamais d'autonomie
    if game.anti_cheat in (AntiCheat.PRESENT, AntiCheat.UNKNOWN):
        if auth.kind is not AuthorizationKind.PUBLISHER_PERMISSION or not has_evidence:
            error(
                "P006",
                "anti-cheat présent ou inconnu : exige une permission explicite de l'éditeur, "
                "avec preuve. BLACKFORGE ne contourne ni ne neutralise aucun anti-cheat",
            )
        if limits.autonomous_allowed or limits.default_autonomy is Autonomy.AUTONOMOUS:
            error("P007", "anti-cheat présent ou inconnu : le mode autonome est interdit")
    # P008 — permissions déclarées pour chaque action et méthode de capture
    declared = set(manifest.permissions)
    for action in manifest.actions:
        needed = ACTION_PERMISSION[action.type]
        if needed is not None and needed not in declared:
            error(
                "P008", f"l'action « {action.type.value} » exige la permission « {needed.value} »"
            )
    for method in manifest.capture_methods:
        needed = CAPTURE_PERMISSION[method]
        if needed not in declared:
            error("P008", f"la capture « {method.value} » exige la permission « {needed.value} »")
    # P009 — canal de test local réservé aux jeux de test ou développés par l'utilisateur
    if any(
        a.type is ActionType.TEST_HARNESS_COMMAND for a in manifest.actions
    ) and game.mode not in (
        GameMode.TEST_ENVIRONMENT,
        GameMode.USER_DEVELOPED,
    ):
        error(
            "P009",
            "« test_harness_command » est réservé aux modes test_environment et user_developed",
        )
    # P010 — plafonds de débit cohérents
    for action in manifest.actions:
        if action.max_per_minute > limits.max_actions_per_minute:
            error(
                "P010",
                f"« {action.type.value} » ({action.max_per_minute}/min) dépasse la limite globale "
                f"({limits.max_actions_per_minute}/min)",
            )
    if (
        limits.max_actions_per_minute > SDK_MAX_ACTIONS_PER_MINUTE
    ):  # pragma: no cover - borné par le schéma
        error("P010", f"limite globale > plafond du SDK ({SDK_MAX_ACTIONS_PER_MINUTE}/min)")
    # P011 — autonomie par défaut cohérente
    if limits.default_autonomy is Autonomy.AUTONOMOUS and not limits.autonomous_allowed:
        error("P011", "default_autonomy « autonomous » alors que autonomous_allowed est faux")
    # P012 — le profil de vision exige la capacité correspondante
    if manifest.vision.detectors and not set(manifest.capabilities) & SUPPORTED_CAPABILITIES:
        error(
            "P012",
            "le profil de vision exige la capacité « detect_objects » ou « recognize_interface »",
        )
    # P013 — tout fichier référencé doit être scellé (SHA-256)
    for path in manifest.vision.referenced_files():
        if path not in manifest.files:
            error(
                "P013",
                f"le fichier « {path} » est référencé mais absent de « files » (empreinte requise)",
            )
    # P014 — pas de scellé orphelin : on n'accepte pas de fichiers non référencés (surface inutile)
    for path in manifest.files:
        if path not in manifest.vision.referenced_files():
            error("P014", f"le fichier « {path} » est scellé mais jamais référencé")

    # --- Avertissements ----------------------------------------------------------------------
    for capability in manifest.capabilities:
        if capability not in SUPPORTED_CAPABILITIES:
            warning(
                "W001",
                f"capacité « {capability.value} » déclarée mais pas encore fournie par cette version des moteurs",
            )
    used = {ACTION_PERMISSION[a.type] for a in manifest.actions} | {
        CAPTURE_PERMISSION[m] for m in manifest.capture_methods
    }
    for permission in sorted(declared - used, key=lambda p: p.value):
        warning(
            "W002",
            f"permission « {permission.value} » déclarée mais inutilisée (moindre privilège)",
        )
    if input_actions and limits.autonomous_allowed:
        warning(
            "W003",
            "actions de saisie en mode autonome : vérifier que le jeu l'autorise explicitement",
        )
    return PolicyReport(plugin_id=manifest.id, violations=tuple(found))


def resolve_autonomy(manifest: PluginManifest, requested: Autonomy | None = None) -> Autonomy:
    """Mode d'autonomie effectif d'un projet. Refuse explicitement, ne dégrade JAMAIS en silence.

    ``requested=None`` → mode par défaut du plugin. Demander « autonomous » sur un plugin qui ne
    l'autorise pas lève ``PolicyDeniedError`` : le projet doit choisir « supervised » en connaissance de cause.
    """
    mode = requested or manifest.limits.default_autonomy
    if mode is Autonomy.AUTONOMOUS and not manifest.limits.autonomous_allowed:
        msg = f"le plugin « {manifest.id} » n'autorise pas le mode autonome"
        raise PolicyDeniedError(msg)
    return mode
