"""Callback query handlers for inline keyboards."""

import asyncio

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings
from app.db.database import get_session_context
from app.db import crud
from app.db.models import JobStatus, SceneStatus
from app.bot.keyboards import (
    get_script_review_keyboard,
    get_final_review_keyboard,
    get_cancel_keyboard,
    get_scene_selection_keyboard,
)
from app.schemas.script import Script, SceneScript
from app.services.script_generator import generate_script
from app.services.script_parser import format_script_for_display
from app.schemas.script import ScriptGenerationRequest
from app.api.render_queue import process_mock_render

logger = structlog.get_logger()


async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle script approval callback."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    logger.info("Script approved via callback", job_id=job_id)

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden")
            return

        if job.status != JobStatus.SCRIPT_PENDING_REVIEW.value:
            await query.message.edit_text(f"❌ Falscher Status: {job.status}")
            return

        # Approve script
        await crud.update_job_status(session, job_id, JobStatus.SCRIPT_APPROVED)

    await query.message.edit_text(
        f"✅ Skript genehmigt!\n\n🎬 Rendering startet...",
        parse_mode="Markdown",
    )

    # Start mock render in background
    settings = get_settings()
    if settings.mock_render:
        asyncio.create_task(run_mock_render_and_notify(job_id, query.message))


async def run_mock_render_and_notify(job_id: str, message) -> None:
    """Run mock render and notify user when done."""
    try:
        await process_mock_render(job_id)

        async with get_session_context() as session:
            job = await crud.get_job(session, job_id)
            if job and job.status == JobStatus.FINAL_PENDING_REVIEW.value:
                await message.reply_text(
                    f"🎬 Video fertig!\n\n"
                    f"Job: `{job_id[:8]}`\n"
                    f"Titel: {job.title}\n\n"
                    f"Review und freigeben:",
                    parse_mode="Markdown",
                    reply_markup=get_final_review_keyboard(job_id, len(job.scenes)),
                )
    except Exception as e:
        logger.error("Mock render failed", job_id=job_id, error=str(e))
        await message.reply_text(f"❌ Render fehlgeschlagen: {e}")


async def handle_regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle script regeneration callback."""
    query = update.callback_query
    if query is None:
        return

    await query.answer("Generiere neues Skript...")

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    logger.info("Script regeneration requested", job_id=job_id)

    await query.message.edit_text("🤖 Generiere neues Skript...")

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden")
            return

        # Delete existing scenes
        for scene in job.scenes:
            await session.delete(scene)
        await session.flush()

        # Reset to generating state
        await crud.update_job_status(session, job_id, JobStatus.SCRIPT_GENERATING)

        try:
            # Generate new script
            request = ScriptGenerationRequest(briefing=job.briefing)
            script = await generate_script(request)

            # Create new scenes
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

            # Update job
            await crud.update_job(
                session,
                job_id,
                title=script.title,
                total_duration_sec=script.total_duration_sec,
                status=JobStatus.SCRIPT_PENDING_REVIEW.value,
            )

            await query.message.edit_text(
                format_script_for_display(script),
                parse_mode="Markdown",
                reply_markup=get_script_review_keyboard(job_id),
            )

        except Exception as e:
            logger.error("Script regeneration failed", job_id=job_id, error=str(e))
            await crud.update_job_status(
                session, job_id, JobStatus.FAILED, error_message=str(e)
            )
            await query.message.edit_text(f"❌ Skript-Generierung fehlgeschlagen: {e}")


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle cancel callback - show confirmation."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    await query.message.edit_text(
        f"⚠️ Job `{job_id[:8]}` wirklich abbrechen?",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(job_id),
    )


async def handle_confirm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle confirmed cancel callback."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    logger.info("Job cancelled via callback", job_id=job_id)

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden")
            return

        await crud.update_job_status(session, job_id, JobStatus.CANCELLED)

    await query.message.edit_text(f"🚫 Job `{job_id[:8]}` abgebrochen.", parse_mode="Markdown")


async def handle_keep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'keep' callback - return to previous view."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden")
            return

        status = JobStatus(job.status)

        if status == JobStatus.SCRIPT_PENDING_REVIEW:
            script = Script(
                title=job.title or "",
                total_duration_sec=job.total_duration_sec,
                character_key=job.character_key,
                scenes=[
                    SceneScript(
                        order=s.order,
                        duration_sec=s.duration_sec,
                        location_key=s.location_key,
                        location_prompt=s.location_prompt,
                        camera_key=s.camera_key,
                        action_key=s.action_key,
                        voiceover_de=s.voiceover_de,
                        needs_lipsync=s.needs_lipsync,
                        caption_overlay=s.caption_overlay,
                        caption_position=s.caption_position,
                    )
                    for s in job.scenes
                ],
            )
            await query.message.edit_text(
                format_script_for_display(script),
                parse_mode="Markdown",
                reply_markup=get_script_review_keyboard(job_id),
            )
        elif status == JobStatus.FINAL_PENDING_REVIEW:
            await query.message.edit_text(
                f"🎬 Video fertig! Review und freigeben:",
                parse_mode="Markdown",
                reply_markup=get_final_review_keyboard(job_id, len(job.scenes)),
            )
        else:
            await query.message.edit_text(f"Job Status: {status.value}")


async def handle_final_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle final video approval callback."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    logger.info("Final video approved", job_id=job_id)

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden")
            return

        if job.status != JobStatus.FINAL_PENDING_REVIEW.value:
            await query.message.edit_text(f"❌ Falscher Status: {job.status}")
            return

        await crud.update_job_status(session, job_id, JobStatus.COMPLETED)

        # Send final video
        settings = get_settings()
        video_path = settings.jobs_dir / job_id / "final.mp4"

        await query.message.edit_text(
            f"🎉 **Job abgeschlossen!**\n\n"
            f"ID: `{job_id[:8]}`\n"
            f"Titel: {job.title}",
            parse_mode="Markdown",
        )

        if video_path.exists():
            try:
                await query.message.reply_video(
                    video=video_path,
                    caption=f"✅ {job.title or 'Final Video'}",
                )
            except Exception as e:
                logger.error("Failed to send video", job_id=job_id, error=str(e))
                await query.message.reply_text(
                    f"Video kann hier heruntergeladen werden:\n"
                    f"`/download {job_id[:8]}`",
                    parse_mode="Markdown",
                )


async def handle_rerender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle scene re-render callback."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    parts = data.split(":")

    if len(parts) < 3:
        await query.message.edit_text("❌ Ungültige Daten")
        return

    job_id = parts[1]
    scene_order = int(parts[2])

    logger.info("Scene re-render requested", job_id=job_id, scene_order=scene_order)

    async with get_session_context() as session:
        scene = await crud.get_scene_by_job_and_order(session, job_id, scene_order)
        if scene is None:
            await query.message.edit_text("❌ Szene nicht gefunden")
            return

        # Reset scene status
        await crud.update_scene_status(session, scene.id, SceneStatus.PENDING)

        job = await crud.get_job(session, job_id)
        if job and job.status == JobStatus.FINAL_PENDING_REVIEW.value:
            await crud.update_job_status(session, job_id, JobStatus.VIDEO_RENDERING)

    await query.message.edit_text(
        f"🔄 Szene {scene_order} wird neu gerendert...",
        parse_mode="Markdown",
    )

    # Start mock render
    settings = get_settings()
    if settings.mock_render:
        asyncio.create_task(run_mock_render_and_notify(job_id, query.message))


async def handle_rerender_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle scene selection for re-render callback."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden")
            return

        await query.message.edit_text(
            "🔄 Welche Szene neu rendern?",
            reply_markup=get_scene_selection_keyboard(job_id, len(job.scenes)),
        )


async def handle_back_to_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle back to review callback."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    job_id = data.split(":")[1] if ":" in data else ""

    if not job_id:
        await query.message.edit_text("❌ Ungültige Job-ID")
        return

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden")
            return

        await query.message.edit_text(
            f"🎬 Video Review\n\nJob: `{job_id[:8]}`",
            parse_mode="Markdown",
            reply_markup=get_final_review_keyboard(job_id, len(job.scenes)),
        )


async def handle_edit_scene(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle edit scene callback - placeholder for future implementation."""
    query = update.callback_query
    if query is None:
        return

    await query.answer("Feature kommt bald!", show_alert=True)
