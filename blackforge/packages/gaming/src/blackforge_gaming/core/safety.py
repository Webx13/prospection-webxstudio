from __future__ import annotations

import threading


class EmergencyStop(RuntimeError):
    """Levée quand l'arrêt d'urgence a été déclenché : toute opération doit s'interrompre."""


class KillSwitch:
    """Arrêt d'urgence partagé entre tous les moteurs d'un runtime.

    Une fois déclenché il reste actif jusqu'à un ``reset()`` explicite, qui doit résulter
    d'une action humaine. Thread-safe : il peut être déclenché depuis l'interface, un signal
    système ou un thread de surveillance.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None
        self._lock = threading.Lock()

    def trigger(self, reason: str) -> None:
        with self._lock:
            if not self._event.is_set():
                self._reason = reason
            self._event.set()

    def reset(self) -> None:
        with self._lock:
            self._reason = None
            self._event.clear()

    @property
    def is_triggered(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    def raise_if_triggered(self) -> None:
        if self._event.is_set():
            msg = f"arrêt d'urgence : {self.reason or 'raison non précisée'}"
            raise EmergencyStop(msg)
