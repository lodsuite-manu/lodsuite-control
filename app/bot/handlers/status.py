"""Handler for /status command."""

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from app.db.database import get_session_context
from app.db import crud
from app.db.models import JobStatus
from app.bot.keyboards import (
    format_status_indicator,
    get_script_review_keyboard,
    get_final_review_keyboard,
)
from app.services.script_parser import format_script_for_display
from app.services.state_machine import get_status_description

logger = structlog.get_logger()


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - show job status."""
    if update.effective_user is None or update.message is None:
        return

    user_id = update.effective_user.id

    # Get job ID from command
    if not context.args:
        await update.message.reply_text(
            "❌ Bitte gib eine Job-ID an.\n\nBeispiel: `/status abc123`",
            parse_mode="Markdown",
        )
        return

    job_id_arg = context.args[0]

    logger.info("Status requested", user_id=user_id, job_id=job_id_arg)

    async with get_session_context() as session:
        # Try exact match first, then prefix
        job = await crud.get_job(session, job_id_arg)
        if job is None and len(job_id_arg) >= 6:
            job = await crud.get_job_by_prefix(session, job_id_arg)

        if job is None:
            await update.message.reply_text(
                f"❌ Job nicht gefunden: `{job_id_arg}`",
                parse_mode="Markdown",
            )
            return

        # Check ownership
        if job.telegram_user_id != user_id:
            await update.message.reply_text("❌ Dieser Job gehört dir nicht.")
            return

        # Build status message
        status = JobStatus(job.status)
        emoji = format_status_indicator(status)
        status_desc = get_status_description(status)

        lines = [
            f"{emoji} **Job Status**",
            f"ID: `{job.id[:8]}`",
            f"Titel: {job.title or 'Unbenannt'}",
            f"Status: {status_desc}",
            f"Erstellt: {job.created_at.strftime('%d.%m.%Y %H:%M')}",
            "",
        ]

        # Add scene info if available
        if job.scenes:
            lines.append(f"📎 {len(job.scenes)} Szenen | {job.total_duration_sec:.0f}s")
            lines.append("")

        # Add error message if failed
        if status == JobStatus.FAILED and job.error_message:
            lines.append(f"⚠️ Fehler: {job.error_message}")
            lines.append("")

        # Determine appropriate keyboard
        keyboard = None
        if status == JobStatus.SCRIPT_PENDING_REVIEW:
            # Show script details and review keyboard
            from app.schemas.script import Script, SceneScript

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
            lines.append(format_script_for_display(script))
            keyboard = get_script_review_keyboard(job.id)

        elif status == JobStatus.FINAL_PENDING_REVIEW:
            lines.append("🎬 Video fertig! Review und freigeben:")
            keyboard = get_final_review_keyboard(job.id, len(job.scenes))

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel command - cancel a job."""
    if update.effective_user is None or update.message is None:
        return

    user_id = update.effective_user.id

    # Get job ID from command
    if not context.args:
        await update.message.reply_text(
            "❌ Bitte gib eine Job-ID an.\n\nBeispiel: `/cancel abc123`",
            parse_mode="Markdown",
        )
        return

    job_id_arg = context.args[0]

    logger.info("Cancel requested", user_id=user_id, job_id=job_id_arg)

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id_arg)
        if job is None and len(job_id_arg) >= 6:
            job = await crud.get_job_by_prefix(session, job_id_arg)

        if job is None:
            await update.message.reply_text(
                f"❌ Job nicht gefunden: `{job_id_arg}`",
                parse_mode="Markdown",
            )
            return

        if job.telegram_user_id != user_id:
            await update.message.reply_text("❌ Dieser Job gehört dir nicht.")
            return

        status = JobStatus(job.status)
        if status in [JobStatus.COMPLETED, JobStatus.CANCELLED]:
            await update.message.reply_text(
                f"❌ Job kann nicht abgebrochen werden (Status: {status.value})"
            )
            return

        # Cancel the job
        await crud.update_job_status(session, job.id, JobStatus.CANCELLED)

        await update.message.reply_text(
            f"🚫 Job `{job.id[:8]}` abgebrochen.",
            parse_mode="Markdown",
        )
