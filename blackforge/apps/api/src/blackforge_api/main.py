"""Fabrique d'application.

Lancement : ``uvicorn blackforge_api.main:create_app --factory``
(aucun effet de bord à l'import : la configuration n'est lue qu'à l'appel).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from blackforge_api.api import health
from blackforge_api.api.v1.router import api_v1
from blackforge_api.core.config import Settings, get_settings, package_version
from blackforge_api.core.errors import install_error_handlers
from blackforge_api.core.logging import configure_logging
from blackforge_api.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from blackforge_api.core.ratelimit import RateLimitMiddleware
from blackforge_api.db.session import create_engine, create_session_factory

logger = logging.getLogger("blackforge.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        logger.info("startup", extra={"env": settings.app_env, "version": package_version()})
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("shutdown")

    app = FastAPI(
        title="BLACKFORGE API",
        version=package_version(),
        summary="Plateforme de création de bots, scripts et automatisations.",
        lifespan=lifespan,
        docs_url="/api/v1/docs" if settings.docs_enabled else None,
        openapi_url="/api/v1/openapi.json" if settings.docs_enabled else None,
        redoc_url=None,
    )
    app.state.settings = settings

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1)

    # add_middleware empile de l'intérieur vers l'extérieur : le dernier ajouté est le plus externe.
    if settings.rate_limit_per_minute > 0:
        app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        allow_credentials=False,
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    return app
