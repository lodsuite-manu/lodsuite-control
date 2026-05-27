"""Handler for /start command."""

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings

logger = structlog.get_logger()

WELCOME_MESSAGE = """👋 Willkommen bei Lodsuite!

Ich helfe dir, AI-generierte B2B-Video-Ads im POV-Selfie-Stil zu erstellen.

**Verfügbare Befehle:**
/new - Neuen Job starten
/new structured - Strukturierte Skript-Erstellung
/new file - YAML-Skript hochladen
/jobs - Deine Jobs anzeigen
/status <id> - Job-Status abfragen
/cancel <id> - Job abbrechen

**So funktioniert's:**
1. Starte mit /new und beschreibe dein Briefing
2. Ich generiere ein Skript, das du reviewen kannst
3. Nach deiner Freigabe wird das Video gerendert
4. Du bekommst das fertige Video zum Download

Bereit? Starte mit /new!
"""

NOT_AUTHORIZED_MESSAGE = """⚠️ Du bist nicht autorisiert, diesen Bot zu nutzen.

Kontaktiere den Administrator für Zugang.
"""


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if update.effective_user is None or update.message is None:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"

    logger.info("Start command received", user_id=user_id, username=username)

    # Check if user is authorized
    settings = get_settings()
    if settings.admin_user_ids and user_id not in settings.admin_user_ids:
        await update.message.reply_text(NOT_AUTHORIZED_MESSAGE)
        logger.warning("Unauthorized user attempted access", user_id=user_id)
        return

    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")
