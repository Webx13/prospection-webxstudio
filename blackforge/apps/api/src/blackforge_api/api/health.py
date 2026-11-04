"""Sondes d'infrastructure (hors /api/v1, jamais soumises au rate limiting)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from blackforge_api.db.session import ping_database

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]


@router.get("/healthz", response_model=Liveness, summary="Liveness : le processus répond")
async def healthz() -> Liveness:
    return Liveness(status="ok")


@router.get(
    "/readyz",
    response_model=Readiness,
    responses={503: {"model": Readiness, "description": "Une dépendance est indisponible"}},
    summary="Readiness : les dépendances (base de données) répondent",
)
async def readyz(request: Request) -> JSONResponse:
    database_ok = await ping_database(request.app.state.engine)
    body = Readiness(
        status="ok" if database_ok else "unavailable",
        database="ok" if database_ok else "unavailable",
    )
    return JSONResponse(body.model_dump(), status_code=200 if database_ok else 503)
