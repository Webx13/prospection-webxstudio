"""Game Plugin SDK : ajouter un jeu = fournir des DONNÉES validées, sans modifier le cœur.

Un plugin déclare identité, plateformes, version, capacités, APIs, méthodes de capture, actions
permises, permissions et limites ; la politique de conformité le valide avant tout usage.
"""

from blackforge_gaming.plugin.loader import (
    LoadedPlugin,
    PluginRejectedError,
    load_plugin,
    parse_manifest,
    sha256_file,
)
from blackforge_gaming.plugin.manifest import (
    ActionSpec,
    ApiSpec,
    Authorization,
    GameInfo,
    Limits,
    PluginManifest,
)
from blackforge_gaming.plugin.policy import (
    PolicyDeniedError,
    PolicyReport,
    PolicyViolation,
    evaluate_policy,
    resolve_autonomy,
)
from blackforge_gaming.plugin.profile import (
    ColorDetectorSpec,
    OnnxDetectorSpec,
    RegionSpec,
    TemplateDetectorSpec,
    VisionProfile,
)
from blackforge_gaming.plugin.vocab import (
    ActionType,
    AntiCheat,
    ApiKind,
    AuthorizationKind,
    Autonomy,
    CaptureMethod,
    GameCapability,
    GameMode,
    Permission,
    Platform,
)

__all__ = [
    "ActionSpec",
    "ActionType",
    "AntiCheat",
    "ApiKind",
    "ApiSpec",
    "Authorization",
    "AuthorizationKind",
    "Autonomy",
    "CaptureMethod",
    "ColorDetectorSpec",
    "GameCapability",
    "GameInfo",
    "GameMode",
    "Limits",
    "LoadedPlugin",
    "OnnxDetectorSpec",
    "Permission",
    "Platform",
    "PluginManifest",
    "PluginRejectedError",
    "PolicyDeniedError",
    "PolicyReport",
    "PolicyViolation",
    "RegionSpec",
    "TemplateDetectorSpec",
    "VisionProfile",
    "evaluate_policy",
    "load_plugin",
    "parse_manifest",
    "resolve_autonomy",
    "sha256_file",
]
