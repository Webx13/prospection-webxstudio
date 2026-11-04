from fastapi import APIRouter

from blackforge_api.api.v1 import system

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(system.router)
