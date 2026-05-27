"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.router import api_router
from app.config import get_settings
from app.db.database import close_db, init_db
from app.services.library import get_library


def configure_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger = structlog.get_logger()

    # Startup
    logger.info("Starting Lodsuite Control Plane")

    settings = get_settings()
    settings.ensure_directories()

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Load asset library
    library = get_library()
    logger.info(
        "Asset library loaded",
        locations=len(library.locations),
        cameras=len(library.cameras),
        actions=len(library.actions),
    )

    logger.info(
        "Startup complete",
        mock_render=settings.mock_render,
        mock_script=settings.mock_script,
    )

    yield

    # Shutdown
    logger.info("Shutting down Lodsuite Control Plane")
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()

    app = FastAPI(
        title="Lodsuite Control Plane",
        description="UGC Ad Pipeline - Control Plane API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(api_router)

    # Serve static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/")
        async def index():
            return FileResponse(static_dir / "index.html")

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
