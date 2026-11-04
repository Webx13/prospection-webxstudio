"""Limiteur de débit par « seau à jetons », en mémoire.

Limites assumées (voir docs/03-SECURITY.md) : état local à chaque processus et clé = adresse
client. Derrière un reverse proxy, lancer uvicorn avec ``--proxy-headers`` et
``--forwarded-allow-ips`` restreint au proxy de confiance, sinon toutes les requêtes
partagent l'adresse du proxy. En production multi-instances, passer à un stockage partagé
(Redis) — le contrat de ``TokenBuckets`` est volontairement minimal pour le permettre.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send

from blackforge_api.core.errors import error_response

_MAX_TRACKED_KEYS = 50_000


class TokenBuckets:
    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(per_minute)
        self.refill_per_second = per_minute / 60.0
        self._clock = clock
        self._state: dict[str, tuple[float, float]] = {}  # clé -> (jetons, dernier passage)

    def take(self, key: str) -> tuple[bool, float]:
        """Consomme un jeton. Retourne ``(autorisé, secondes_avant_nouvel_essai)``."""
        now = self._clock()
        tokens, last = self._state.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)
        if tokens >= 1.0:
            self._state[key] = (tokens - 1.0, now)
            self._evict_if_needed(now)
            return True, 0.0
        self._state[key] = (tokens, now)
        return False, (1.0 - tokens) / self.refill_per_second

    def _evict_if_needed(self, now: float) -> None:
        if len(self._state) <= _MAX_TRACKED_KEYS:
            return
        # Les seaux revenus pleins sont indiscernables d'un client inconnu : on les oublie.
        full_after = self.capacity / self.refill_per_second
        for key in [k for k, (_, last) in self._state.items() if now - last >= full_after]:
            del self._state[key]


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        per_minute: int,
        prefix: str = "/api/",
        buckets: TokenBuckets | None = None,
    ) -> None:
        self.app = app
        self._prefix = prefix
        self._buckets = buckets or TokenBuckets(per_minute)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Les health checks (hors /api/) ne sont jamais limités : les orchestrateurs les sondent.
        if scope["type"] != "http" or not scope["path"].startswith(self._prefix):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        allowed, retry_after = self._buckets.take(key)
        if allowed:
            await self.app(scope, receive, send)
            return

        response = error_response(
            429,
            "rate_limited",
            "Trop de requêtes. Réessayez dans quelques instants.",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
        await response(scope, receive, send)
