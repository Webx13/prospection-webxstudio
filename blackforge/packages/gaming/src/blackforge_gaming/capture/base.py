from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from blackforge_gaming.core.frame import Frame


class CaptureUnavailableError(RuntimeError):
    """Le backend de capture ne peut pas fonctionner ici (pas d'affichage, permission OS…)."""


class FrameSourceBase(ABC):
    """Gère le cycle de vie (open/read/close idempotents) ; les sous-classes fournissent le reste."""

    def __init__(self) -> None:
        self._opened = False
        self._next_index = 0

    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    def _open(self) -> None: ...

    @abstractmethod
    def _read(self) -> Frame | None: ...

    @abstractmethod
    def _close(self) -> None: ...

    def open(self) -> None:
        if self._opened:
            return
        self._open()
        self._opened = True

    def read(self) -> Frame | None:
        if not self._opened:
            msg = f"{type(self).__name__}.read() appelé avant open()"
            raise RuntimeError(msg)
        return self._read()

    def close(self) -> None:
        if not self._opened:
            return
        self._opened = False
        self._close()

    def _take_index(self) -> int:
        index = self._next_index
        self._next_index += 1
        return index

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
