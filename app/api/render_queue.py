"""Render queue endpoints for GPU worker communication."""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import crud
from app.db.database import get_session
from app.db.models import JobStatus, SceneStatus
from app.schemas.job import RenderTaskResponse, SceneStatusUpdate, VariantUploadResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["render"])


@router.get("/render-queue/next", response_model=Optional[RenderTaskResponse])
async def get_next_render_task(
    session: AsyncSession = Depends(get_session),
) -> Optional[RenderTaskResponse]:
    """Get the next render task from the queue.

    Returns 204 No Content if no tasks are available.
    """
    task = await crud.get_next_render_task(session)

    if task is None:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)

    # Mark scene as rendering
    await crud.update_scene_status(session, task["scene_id"], SceneStatus.RENDERING)

    logger.info(
        "Render task dispatched",
        job_id=task["job_id"],
        scene_order=task["scene_order"],
    )

    return RenderTaskResponse(**task)


@router.post("/jobs/{job_id}/scene/{scene_order}/status")
async def update_scene_status(
    job_id: str,
    scene_order: int,
    update: SceneStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update scene status from render worker."""
    scene = await crud.get_scene_by_job_and_order(session, job_id, scene_order)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: job={job_id}, order={scene_order}",
        )

    # Convert string to enum if needed
    status_enum = SceneStatus(update.status) if isinstance(update.status, str) else update.status
    await crud.update_scene_status(session, scene.id, status_enum)

    logger.info(
        "Scene status updated",
        job_id=job_id,
        scene_order=scene_order,
        status=update.status,
    )

    return {"status": "ok"}


@router.post("/jobs/{job_id}/scene/{scene_order}/variant", response_model=VariantUploadResponse)
async def upload_scene_variant(
    job_id: str,
    scene_order: int,
    idx: int,
    seed: int,
    duration_sec: float,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> VariantUploadResponse:
    """Upload a scene variant from render worker."""
    scene = await crud.get_scene_by_job_and_order(session, job_id, scene_order)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: job={job_id}, order={scene_order}",
        )

    # Save file
    settings = get_settings()
    job_dir = settings.jobs_dir / job_id / "scenes" / str(scene_order)
    job_dir.mkdir(parents=True, exist_ok=True)

    video_path = job_dir / f"variant_{idx}.mp4"
    with open(video_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Create variant record
    variant = await crud.create_scene_variant(
        session=session,
        scene_id=scene.id,
        idx=idx,
        video_path=str(video_path),
        seed=seed,
        duration_sec=duration_sec,
    )

    logger.info(
        "Variant uploaded",
        job_id=job_id,
        scene_order=scene_order,
        idx=idx,
    )

    return VariantUploadResponse(
        variant_id=variant.id,
        scene_id=scene.id,
        idx=idx,
        video_path=str(video_path),
    )


@router.post("/jobs/{job_id}/audio")
async def upload_master_audio(
    job_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload master audio track for job."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    settings = get_settings()
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    audio_path = job_dir / "master_audio.mp3"
    with open(audio_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info("Master audio uploaded", job_id=job_id)

    return {"status": "ok", "path": str(audio_path)}


@router.post("/jobs/{job_id}/final")
async def upload_final_video(
    job_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload final assembled video."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    settings = get_settings()
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    video_path = job_dir / "final.mp4"
    with open(video_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Update job status
    await crud.update_job_status(session, job_id, JobStatus.FINAL_PENDING_REVIEW)

    logger.info("Final video uploaded", job_id=job_id)

    return {"status": "ok", "path": str(video_path)}


# Mock render functionality for Phase 1


def create_mock_video(output_path: Path, duration: int = 5, text: str = "") -> None:
    """Create a mock black video with optional text overlay."""
    # Build filter for text overlay
    if text:
        # Escape special characters for ffmpeg
        escaped_text = text.replace("'", "'\\''").replace(":", "\\:")
        video_filter = (
            f"color=black:s=1080x1920:d={duration},"
            f"drawtext=text='{escaped_text}':fontcolor=white:fontsize=48:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )
    else:
        video_filter = f"color=black:s=1080x1920:d={duration}"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", video_filter,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(duration),
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.debug("Mock video created", path=str(output_path))
    except subprocess.CalledProcessError as e:
        logger.error("Failed to create mock video", error=e.stderr.decode())
        raise


async def process_mock_render(job_id: str) -> None:
    """Simulate render by creating mock videos after delay."""
    from app.db.database import get_session_context

    settings = get_settings()

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            logger.error("Job not found for mock render", job_id=job_id)
            return

        # Update to video rendering
        await crud.update_job_status(session, job_id, JobStatus.VIDEO_RENDERING)

        job_dir = settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Simulate rendering each scene
        total_duration = 0
        for scene in job.scenes:
            await crud.update_scene_status(session, scene.id, SceneStatus.RENDERING)

            # Simulate render time
            await asyncio.sleep(1)

            # Create mock variant
            scene_dir = job_dir / "scenes" / str(scene.order)
            scene_dir.mkdir(parents=True, exist_ok=True)

            variant_path = scene_dir / "variant_0.mp4"
            create_mock_video(
                variant_path,
                duration=int(scene.duration_sec),
                text=f"Scene {scene.order}",
            )

            # Create variant record
            await crud.create_scene_variant(
                session=session,
                scene_id=scene.id,
                idx=0,
                video_path=str(variant_path),
                seed=12345,
                duration_sec=scene.duration_sec,
            )

            await crud.update_scene_status(session, scene.id, SceneStatus.READY)
            total_duration += scene.duration_sec

        # Progress through render states
        for state in [
            JobStatus.AUDIO_RENDERING,
            JobStatus.LIPSYNC_RUNNING,
            JobStatus.ASSEMBLY_RUNNING,
        ]:
            await crud.update_job_status(session, job_id, state)
            await asyncio.sleep(0.5)

        # Create final mock video
        final_path = job_dir / "final.mp4"
        create_mock_video(
            final_path,
            duration=int(total_duration),
            text=job.title or "Final Video",
        )

        # Complete
        await crud.update_job_status(session, job_id, JobStatus.FINAL_PENDING_REVIEW)

        logger.info(
            "Mock render completed",
            job_id=job_id,
            duration=total_duration,
        )
