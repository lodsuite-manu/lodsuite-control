"""Job CRUD endpoints."""

from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import crud
from app.db.database import get_session
from app.db.models import JobStatus, SceneStatus
from app.schemas.job import JobCreateRequest, JobListResponse, JobResponse
from app.schemas.script import Script, ScriptGenerationRequest
from app.services.script_generator import generate_script
from app.services.script_parser import format_script_for_display
from app.services.state_machine import can_transition, validate_transition

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: JobCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Create a new job."""
    job = await crud.create_job(
        session=session,
        telegram_user_id=request.telegram_user_id,
        telegram_chat_id=request.telegram_chat_id,
        briefing=request.briefing,
        mode=request.mode,
        character_key=request.character_key,
    )

    logger.info(
        "Job created",
        job_id=job.id,
        user_id=request.telegram_user_id,
        mode=request.mode,
    )

    # Re-fetch with eager loading to avoid lazy load issues
    job = await crud.get_job(session, job.id)
    return JobResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    user_id: Optional[int] = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> JobListResponse:
    """List jobs, optionally filtered by user."""
    if user_id:
        jobs = await crud.get_jobs_by_user(session, user_id, limit=limit)
    else:
        jobs = await crud.get_all_jobs(session, limit=limit)

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=len(jobs),
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Get job by ID or prefix."""
    # Try exact match first
    job = await crud.get_job(session, job_id)

    # Try prefix match if not found
    if job is None and len(job_id) >= 6:
        job = await crud.get_job_by_prefix(session, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    return JobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete/cancel a job."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    # Update status to cancelled if not already terminal
    if job.status not in [JobStatus.COMPLETED.value, JobStatus.CANCELLED.value]:
        await crud.update_job_status(session, job_id, JobStatus.CANCELLED)

    logger.info("Job cancelled", job_id=job_id)


@router.post("/{job_id}/script/generate", response_model=JobResponse)
async def generate_job_script(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Generate script for a job."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    # Validate state transition
    current_status = JobStatus(job.status)
    if not can_transition(current_status, JobStatus.SCRIPT_GENERATING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate script in state: {job.status}",
        )

    # Update status
    await crud.update_job_status(session, job_id, JobStatus.SCRIPT_GENERATING)

    try:
        # Generate script
        request = ScriptGenerationRequest(
            briefing=job.briefing,
            character_key=job.character_key,
        )
        script = await generate_script(request)

        # Create scenes from script
        for scene_script in script.scenes:
            await crud.create_scene(
                session=session,
                job_id=job_id,
                order=scene_script.order,
                duration_sec=scene_script.duration_sec,
                location_key=scene_script.location_key,
                location_prompt=scene_script.location_prompt,
                camera_key=scene_script.camera_key,
                action_key=scene_script.action_key,
                voiceover_de=scene_script.voiceover_de,
                needs_lipsync=scene_script.needs_lipsync,
                caption_overlay=scene_script.caption_overlay,
                caption_position=scene_script.caption_position,
            )

        # Update job with script details
        await crud.update_job(
            session,
            job_id,
            title=script.title,
            total_duration_sec=script.total_duration_sec,
            status=JobStatus.SCRIPT_PENDING_REVIEW.value,
        )

        logger.info(
            "Script generated",
            job_id=job_id,
            title=script.title,
            scenes=len(script.scenes),
        )

    except Exception as e:
        logger.error("Script generation failed", job_id=job_id, error=str(e))
        await crud.update_job_status(
            session, job_id, JobStatus.FAILED, error_message=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Script generation failed: {e}",
        )

    # Refresh job
    job = await crud.get_job(session, job_id)
    return JobResponse.model_validate(job)


@router.post("/{job_id}/script/approve", response_model=JobResponse)
async def approve_script(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Approve the generated script and start rendering."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    current_status = JobStatus(job.status)
    if current_status != JobStatus.SCRIPT_PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve script in state: {job.status}",
        )

    # Transition to approved
    await crud.update_job_status(session, job_id, JobStatus.SCRIPT_APPROVED)

    logger.info("Script approved", job_id=job_id)

    job = await crud.get_job(session, job_id)
    return JobResponse.model_validate(job)


@router.post("/{job_id}/script/regenerate", response_model=JobResponse)
async def regenerate_script(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Regenerate the script."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    current_status = JobStatus(job.status)
    if current_status != JobStatus.SCRIPT_PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot regenerate script in state: {job.status}",
        )

    # Delete existing scenes
    for scene in job.scenes:
        await session.delete(scene)
    await session.flush()

    # Reset to generating state
    await crud.update_job_status(session, job_id, JobStatus.SCRIPT_GENERATING)

    # Re-generate
    return await generate_job_script(job_id, session)


@router.post("/{job_id}/final/approve", response_model=JobResponse)
async def approve_final(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Approve the final video."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    current_status = JobStatus(job.status)
    if current_status != JobStatus.FINAL_PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve final in state: {job.status}",
        )

    await crud.update_job_status(session, job_id, JobStatus.COMPLETED)

    logger.info("Final approved, job completed", job_id=job_id)

    job = await crud.get_job(session, job_id)
    return JobResponse.model_validate(job)


@router.post("/{job_id}/scene/{scene_order}/rerender", response_model=JobResponse)
async def rerender_scene(
    job_id: str,
    scene_order: int,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Request re-render of a specific scene."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    scene = await crud.get_scene_by_job_and_order(session, job_id, scene_order)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_order}",
        )

    # Reset scene status
    await crud.update_scene_status(session, scene.id, SceneStatus.PENDING)

    # If job was in final review, go back to rendering
    if job.status == JobStatus.FINAL_PENDING_REVIEW.value:
        await crud.update_job_status(session, job_id, JobStatus.VIDEO_RENDERING)

    logger.info("Scene re-render requested", job_id=job_id, scene_order=scene_order)

    job = await crud.get_job(session, job_id)
    return JobResponse.model_validate(job)


@router.get("/{job_id}/final.mp4")
async def download_final_video(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Download the final video."""
    job = await crud.get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    if job.status not in [JobStatus.COMPLETED.value, JobStatus.FINAL_PENDING_REVIEW.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Final video not ready",
        )

    settings = get_settings()
    video_path = settings.jobs_dir / job_id / "final.mp4"

    if not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Final video file not found",
        )

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"{job.title or 'video'}.mp4",
    )
