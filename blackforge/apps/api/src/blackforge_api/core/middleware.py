"""Middlewares ASGI purs (pas de ``BaseHTTPMiddleware`` : pas de souci avec les flux).

Ordre (extérieur → intérieur) : SecurityHeaders → RequestContext → CORS → RateLimit → routes.
``RequestContext`` convertit lui-même les exceptions non gérées en 500 : le handler
``Exception`` de Starlette s'exécute *hors* des middlewares utilisateur, donc sans en-têtes
ni identifiant de requête.
"""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from blackforge_api.core.errors import error_response
from blackforge_api.core.logging import request_id_var

logger = logging.getLogger("blackforge.access")

# Un identifiant entrant n'est repris que s'il est court et sûr (anti-injection de logs).
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._\-]{8,64}")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return str(value.decode("latin-1"))
    return None


class RequestContextMiddleware:
    """Identifiant de requête, journal d'accès structuré et filet de sécurité 500."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and _SAFE_REQUEST_ID.fullmatch(incoming) else uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                logger.exception("unhandled_exception", extra={"path": scope["path"]})
                if response_started:
                    raise
                response = error_response(500, "internal_error", "Erreur interne du serveur.")
                await response(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],  # jamais la query string (peut contenir un jeton)
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)


class SecurityHeadersMiddleware:
    """En-têtes de durcissement pour toutes les réponses de l'API."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self._static = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cross-Origin-Resource-Policy": "same-site",
        }
        if hsts:
            self._static["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self._static.items():
                    headers.setdefault(name, value)
                # Les réponses d'API ne doivent jamais être mises en cache par un intermédiaire.
                headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_wrapper)
