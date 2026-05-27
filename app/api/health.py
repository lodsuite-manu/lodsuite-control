"""Health check endpoint."""

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.job import HealthResponse
from app.services.library import get_library

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        mock_render=settings.mock_render,
        mock_script=settings.mock_script,
    )


@router.get("/api/v1/library")
async def get_asset_library() -> dict:
    """Get available locations, cameras, and actions."""
    library = get_library()
    return {
        "locations": library.locations,
        "cameras": library.cameras,
        "actions": library.actions,
    }
