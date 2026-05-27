"""Handler for /jobs command."""

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from app.db.database import get_session_context
from app.db import crud
from app.db.models import JobStatus
from app.bot.keyboards import format_status_indicator

logger = structlog.get_logger()


async def jobs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /jobs command - list user's jobs."""
    if update.effective_user is None or update.message is None:
        return

    user_id = update.effective_user.id

    logger.info("Jobs list requested", user_id=user_id)

    async with get_session_context() as session:
        jobs = await crud.get_jobs_by_user(session, user_id, limit=10)

        if not jobs:
            await update.message.reply_text(
                "📭 Du hast noch keine Jobs.\n\nStarte mit /new um einen neuen Job zu erstellen."
            )
            return

        lines = ["📋 **Deine Jobs:**\n"]

        for job in jobs:
            status = JobStatus(job.status)
            emoji = format_status_indicator(status)
            short_id = job.id[:8]

            title = job.title or "Unbenannt"
            if len(title) > 25:
                title = title[:22] + "..."

            # Format time
            created = job.created_at.strftime("%d.%m. %H:%M")

            lines.append(f"{emoji} `{short_id}` | {title}")
            lines.append(f"   {status.value.replace('_', ' ').title()} | {created}")
            lines.append("")

        lines.append("💡 Nutze `/status <id>` für Details")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
