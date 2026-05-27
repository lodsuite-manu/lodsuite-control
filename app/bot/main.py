"""Telegram bot entry point."""

import asyncio
import logging

import structlog
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

from app.config import get_settings
from app.db.database import init_db
from app.services.library import get_library
from app.bot.handlers.start import start_handler
from app.bot.handlers.jobs_list import jobs_handler
from app.bot.handlers.status import status_handler, cancel_handler
from app.bot.handlers.new_job import get_new_job_handler
from app.bot.handlers import callbacks


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


async def post_init(application: Application) -> None:
    """Initialize resources after application setup."""
    logger = structlog.get_logger()

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


def main() -> None:
    """Run the Telegram bot."""
    configure_logging()
    logger = structlog.get_logger()

    settings = get_settings()
    settings.ensure_directories()

    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return

    logger.info("Starting Lodsuite Telegram Bot")

    # Build application
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    # Add handlers
    # Command handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", start_handler))
    application.add_handler(CommandHandler("jobs", jobs_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CommandHandler("cancel", cancel_handler))

    # Conversation handler for /new
    application.add_handler(get_new_job_handler())

    # Callback query handlers
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_approve, pattern=r"^approve:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_regenerate, pattern=r"^regenerate:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_cancel, pattern=r"^cancel:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_confirm_cancel, pattern=r"^confirm_cancel:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_keep, pattern=r"^keep:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_final_approve, pattern=r"^final_approve:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_rerender, pattern=r"^rerender:\w+:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_rerender_select, pattern=r"^rerender_select:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_back_to_review, pattern=r"^back_to_review:")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks.handle_edit_scene, pattern=r"^edit:")
    )

    logger.info("Bot handlers registered, starting polling")

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
