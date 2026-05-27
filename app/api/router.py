"""API router aggregation."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.render_queue import router as render_router

api_router = APIRouter()

# Include all routers
api_router.include_router(health_router)
api_router.include_router(jobs_router)
api_router.include_router(render_router)
