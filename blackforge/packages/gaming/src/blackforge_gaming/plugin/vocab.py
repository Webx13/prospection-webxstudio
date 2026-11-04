"""Vocabulaires FERMÉS du SDK de plugins.

C'est le contrôle principal : un plugin ne peut déclarer que ce qui figure ici. Il n'existe aucune
valeur pour « lire la mémoire du jeu », « injecter du code », « contourner un anti-cheat » ou
« masquer l'automatisation » : ces notions ne peuvent pas être exprimées, donc un manifeste qui
les mentionne est refusé à la validation. Un test garantit qu'aucune valeur de ce module ne les
introduit à l'avenir.
"""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    WEB = "web"


class GameMode(StrEnum):
    SINGLE_PLAYER = "single_player"
    TEST_ENVIRONMENT = "test_environment"
    USER_DEVELOPED = "user_developed"
    PRIVATE_SERVER = "private_server"
    ONLINE_MULTIPLAYER = "online_multiplayer"


class AuthorizationKind(StrEnum):
    OWN_GAME = "own_game"
    OFFLINE_SINGLE_PLAYER = "offline_single_player"
    TEST_ENVIRONMENT = "test_environment"
    PRIVATE_SERVER_OPERATOR = "private_server_operator"
    PUBLISHER_PERMISSION = "publisher_permission"
    TERMS_PERMIT_AUTOMATION = "terms_permit_automation"


class AntiCheat(StrEnum):
    NONE = "none"
    PRESENT = "present"
    UNKNOWN = "unknown"  # traité comme « présent » par la politique


class CaptureMethod(StrEnum):
    DISPLAY = "display"
    SCREEN_REGION = "screen_region"
    OFFICIAL_API = "official_api"
    REPLAY_FILE = "replay_file"


class ActionType(StrEnum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    KEY_PRESS = "key_press"
    GAMEPAD_BUTTON = "gamepad_button"
    OFFICIAL_API_CALL = "official_api_call"
    TEST_HARNESS_COMMAND = "test_harness_command"


class Permission(StrEnum):
    CAPTURE_SCREEN = "capture.screen"
    INPUT_MOUSE = "input.mouse"
    INPUT_KEYBOARD = "input.keyboard"
    INPUT_GAMEPAD = "input.gamepad"
    NETWORK_OFFICIAL_API = "network.official_api"
    STORAGE_RECORDINGS = "storage.recordings"


class GameCapability(StrEnum):
    DETECT_OBJECTS = "detect_objects"
    RECOGNIZE_INTERFACE = "recognize_interface"
    READ_TEXT = "read_text"
    TRACK_OBJECTS = "track_objects"


class Autonomy(StrEnum):
    SUPERVISED = "supervised"  # l'agent propose, l'utilisateur valide
    AUTONOMOUS = "autonomous"  # l'agent décide ; le moteur de permissions valide


class ApiKind(StrEnum):
    OFFICIAL = "official"
    LOCAL_TEST_HARNESS = "local_test_harness"


# --- Relations entre vocabulaires --------------------------------------------------------------

ACTION_PERMISSION: dict[ActionType, Permission | None] = {
    ActionType.MOUSE_MOVE: Permission.INPUT_MOUSE,
    ActionType.MOUSE_CLICK: Permission.INPUT_MOUSE,
    ActionType.KEY_PRESS: Permission.INPUT_KEYBOARD,
    ActionType.GAMEPAD_BUTTON: Permission.INPUT_GAMEPAD,
    ActionType.OFFICIAL_API_CALL: Permission.NETWORK_OFFICIAL_API,
    ActionType.TEST_HARNESS_COMMAND: None,  # canal local d'un jeu de test, sans réseau ni périphérique
}

CAPTURE_PERMISSION: dict[CaptureMethod, Permission] = {
    CaptureMethod.DISPLAY: Permission.CAPTURE_SCREEN,
    CaptureMethod.SCREEN_REGION: Permission.CAPTURE_SCREEN,
    CaptureMethod.OFFICIAL_API: Permission.NETWORK_OFFICIAL_API,
    CaptureMethod.REPLAY_FILE: Permission.STORAGE_RECORDINGS,
}

INPUT_ACTIONS = frozenset(
    {ActionType.MOUSE_MOVE, ActionType.MOUSE_CLICK, ActionType.KEY_PRESS, ActionType.GAMEPAD_BUTTON}
)

# Capacités que les moteurs actuels fournissent réellement. Les autres peuvent être déclarées mais
# produisent un avertissement : on ne laisse pas croire qu'une fonction existe.
SUPPORTED_CAPABILITIES = frozenset(
    {GameCapability.DETECT_OBJECTS, GameCapability.RECOGNIZE_INTERFACE}
)
