from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from blackforge_api.core.config import package_version
from blackforge_api.db.session import ping_database

router = APIRouter(prefix="/system", tags=["system"])


class SystemStatus(BaseModel):
    service: Literal["blackforge-api"] = "blackforge-api"
    version: str
    api_version: Literal["v1"] = "v1"
    # « degraded » = l'API répond mais une dépendance est indisponible.
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


@router.get("/status", response_model=SystemStatus, summary="État de la plateforme")
async def system_status(request: Request) -> SystemStatus:
    database_ok = await ping_database(request.app.state.engine)
    return SystemStatus(
        version=package_version(),
        status="ok" if database_ok else "degraded",
        database="ok" if database_ok else "unavailable",
    )
