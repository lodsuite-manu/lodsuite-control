"""Database CRUD operations."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Job, JobMode, JobStatus, Scene, SceneStatus, SceneVariant


async def create_job(
    session: AsyncSession,
    telegram_user_id: int,
    telegram_chat_id: int,
    briefing: str = "",
    mode: str = "brief",
    character_key: str = "markus_industrial",
) -> Job:
    """Create a new job."""
    # Handle both enum and string mode
    mode_value = mode.value if hasattr(mode, 'value') else mode

    job = Job(
        id=str(uuid.uuid4()),
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        briefing=briefing,
        mode=mode_value,
        status=JobStatus.BRIEFING_RECEIVED.value,
        character_key=character_key,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(job)
    await session.flush()
    return job


async def get_job(session: AsyncSession, job_id: str) -> Optional[Job]:
    """Get a job by ID, including scenes and variants."""
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.scenes).selectinload(Scene.variants))
    )
    return result.scalar_one_or_none()


async def get_job_by_prefix(session: AsyncSession, prefix: str) -> Optional[Job]:
    """Get a job by ID prefix (for user-friendly short IDs)."""
    result = await session.execute(
        select(Job)
        .where(Job.id.startswith(prefix))
        .options(selectinload(Job.scenes).selectinload(Scene.variants))
    )
    return result.scalar_one_or_none()


async def get_jobs_by_user(
    session: AsyncSession,
    telegram_user_id: int,
    limit: int = 20,
) -> list[Job]:
    """Get jobs for a specific user."""
    result = await session.execute(
        select(Job)
        .where(Job.telegram_user_id == telegram_user_id)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .options(selectinload(Job.scenes))
    )
    return list(result.scalars().all())


async def get_all_jobs(session: AsyncSession, limit: int = 100) -> list[Job]:
    """Get all jobs."""
    result = await session.execute(
        select(Job)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .options(selectinload(Job.scenes))
    )
    return list(result.scalars().all())


async def update_job_status(
    session: AsyncSession,
    job_id: str,
    status: JobStatus,
    error_message: Optional[str] = None,
) -> Optional[Job]:
    """Update job status."""
    job = await get_job(session, job_id)
    if job is None:
        return None

    job.status = status.value
    job.updated_at = datetime.utcnow()
    if error_message is not None:
        job.error_message = error_message

    await session.flush()
    return job


async def update_job(
    session: AsyncSession,
    job_id: str,
    **kwargs,
) -> Optional[Job]:
    """Update job fields."""
    job = await get_job(session, job_id)
    if job is None:
        return None

    for key, value in kwargs.items():
        if hasattr(job, key):
            setattr(job, key, value)

    job.updated_at = datetime.utcnow()
    await session.flush()
    return job


async def delete_job(session: AsyncSession, job_id: str) -> bool:
    """Delete a job and all related data."""
    job = await get_job(session, job_id)
    if job is None:
        return False

    await session.delete(job)
    await session.flush()
    return True


async def create_scene(
    session: AsyncSession,
    job_id: str,
    order: int,
    duration_sec: float,
    location_key: str,
    location_prompt: str,
    camera_key: str,
    action_key: str,
    voiceover_de: str,
    needs_lipsync: bool = True,
    caption_overlay: Optional[str] = None,
    caption_position: str = "top",
    variant_count: int = 3,
) -> Scene:
    """Create a new scene for a job."""
    scene = Scene(
        job_id=job_id,
        order=order,
        duration_sec=duration_sec,
        location_key=location_key,
        location_prompt=location_prompt,
        camera_key=camera_key,
        action_key=action_key,
        voiceover_de=voiceover_de,
        needs_lipsync=needs_lipsync,
        caption_overlay=caption_overlay,
        caption_position=caption_position,
        variant_count=variant_count,
        status=SceneStatus.PENDING.value,
    )
    session.add(scene)
    await session.flush()
    return scene


async def get_scene(session: AsyncSession, scene_id: int) -> Optional[Scene]:
    """Get a scene by ID."""
    result = await session.execute(
        select(Scene)
        .where(Scene.id == scene_id)
        .options(selectinload(Scene.variants))
    )
    return result.scalar_one_or_none()


async def get_scene_by_job_and_order(
    session: AsyncSession,
    job_id: str,
    order: int,
) -> Optional[Scene]:
    """Get a scene by job ID and order number."""
    result = await session.execute(
        select(Scene)
        .where(Scene.job_id == job_id, Scene.order == order)
        .options(selectinload(Scene.variants))
    )
    return result.scalar_one_or_none()


async def update_scene_status(
    session: AsyncSession,
    scene_id: int,
    status: SceneStatus,
) -> Optional[Scene]:
    """Update scene status."""
    scene = await get_scene(session, scene_id)
    if scene is None:
        return None

    scene.status = status.value
    await session.flush()
    return scene


async def create_scene_variant(
    session: AsyncSession,
    scene_id: int,
    idx: int,
    video_path: str,
    seed: int,
    duration_sec: float,
    thumbnail_path: Optional[str] = None,
) -> SceneVariant:
    """Create a new scene variant."""
    variant = SceneVariant(
        scene_id=scene_id,
        idx=idx,
        video_path=video_path,
        seed=seed,
        duration_sec=duration_sec,
        thumbnail_path=thumbnail_path,
    )
    session.add(variant)
    await session.flush()
    return variant


async def get_pending_render_jobs(session: AsyncSession) -> list[Job]:
    """Get jobs that are ready for rendering."""
    result = await session.execute(
        select(Job)
        .where(
            Job.status.in_([
                JobStatus.SCRIPT_APPROVED.value,
                JobStatus.VIDEO_RENDERING.value,
                JobStatus.AUDIO_RENDERING.value,
                JobStatus.LIPSYNC_RUNNING.value,
                JobStatus.ASSEMBLY_RUNNING.value,
            ])
        )
        .order_by(Job.created_at.asc())
        .options(selectinload(Job.scenes).selectinload(Scene.variants))
    )
    return list(result.scalars().all())


async def get_next_render_task(session: AsyncSession) -> Optional[dict]:
    """Get the next render task from the queue."""
    # Find jobs in render states
    jobs = await get_pending_render_jobs(session)
    if not jobs:
        return None

    for job in jobs:
        # Find scenes that need rendering
        for scene in job.scenes:
            if scene.status == SceneStatus.PENDING.value:
                return {
                    "job_id": job.id,
                    "scene_order": scene.order,
                    "scene_id": scene.id,
                    "task_type": "video_render",
                    "location_key": scene.location_key,
                    "location_prompt": scene.location_prompt,
                    "camera_key": scene.camera_key,
                    "action_key": scene.action_key,
                    "duration_sec": scene.duration_sec,
                    "voiceover_de": scene.voiceover_de,
                    "needs_lipsync": scene.needs_lipsync,
                    "variant_count": scene.variant_count,
                    "character_key": job.character_key,
                }

    return None
