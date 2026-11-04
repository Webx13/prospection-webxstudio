"""Racine de composition : rapport des capacités RÉELLES de la machine courante."""

from __future__ import annotations

import platform
import sys
from dataclasses import asdict, dataclass

from blackforge_gaming.capture import probe_screen_capture
from blackforge_gaming.core.capabilities import Capability
from blackforge_gaming.vision import probe_vision


@dataclass(frozen=True, slots=True)
class SystemReport:
    platform: str
    machine: str
    python: str
    capabilities: tuple[Capability, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["capabilities"] = [
            {"name": c.name, "availability": c.availability.value, "detail": c.detail}
            for c in self.capabilities
        ]
        return data


def build_report() -> SystemReport:
    return SystemReport(
        platform=platform.platform(),
        machine=platform.machine(),
        python=sys.version.split()[0],
        capabilities=(*probe_screen_capture(), *probe_vision()),
    )
