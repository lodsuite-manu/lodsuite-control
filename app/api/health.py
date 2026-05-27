"""Health check endpoint."""

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.job import HealthResponse

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
