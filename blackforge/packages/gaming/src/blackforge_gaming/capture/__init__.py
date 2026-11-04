"""Screen Capture Engine : sources d'images (écran réel soumis à consentement, rejeu)."""

from blackforge_gaming.capture.base import CaptureUnavailableError, FrameSourceBase
from blackforge_gaming.capture.replay import ReplaySource, record_frames
from blackforge_gaming.capture.screen import (
    ScreenCaptureSource,
    macos_screen_recording_permission,
    probe_screen_capture,
)

__all__ = [
    "CaptureUnavailableError",
    "FrameSourceBase",
    "ReplaySource",
    "ScreenCaptureSource",
    "macos_screen_recording_permission",
    "probe_screen_capture",
    "record_frames",
]
