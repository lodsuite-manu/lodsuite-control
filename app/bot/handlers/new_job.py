"""Handler for /new command and job creation flow."""

import asyncio
from enum import Enum, auto
from typing import Optional

import structlog
import yaml
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from app.config import get_settings
from app.db.database import get_session_context
from app.db import crud
from app.db.models import JobMode, JobStatus
from app.bot.keyboards import (
    get_mode_selection_keyboard,
    get_script_review_keyboard,
    get_location_keyboard,
    get_camera_keyboard,
    get_action_keyboard,
    get_lipsync_keyboard,
    get_continue_keyboard,
)
from app.schemas.script import Script, SceneScript, ScriptGenerationRequest
from app.services.script_generator import generate_script
from app.services.script_parser import format_script_for_display, parse_yaml_script
from app.api.render_queue import process_mock_render

logger = structlog.get_logger()


class ConvState(Enum):
    """Conversation states."""

    SELECTING_MODE = auto()
    AWAITING_BRIEFING = auto()
    AWAITING_FILE = auto()
    STRUCTURED_SCENE_COUNT = auto()
    STRUCTURED_LOCATION = auto()
    STRUCTURED_CAMERA = auto()
    STRUCTURED_ACTION = auto()
    STRUCTURED_VOICEOVER = auto()
    STRUCTURED_LIPSYNC = auto()
    STRUCTURED_CONTINUE = auto()


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /new command - start job creation."""
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    user_id = update.effective_user.id

    # Check authorization
    settings = get_settings()
    if settings.admin_user_ids and user_id not in settings.admin_user_ids:
        await update.message.reply_text("⚠️ Nicht autorisiert.")
        return ConversationHandler.END

    # Check for direct mode selection
    text = update.message.text or ""
    if "structured" in text.lower():
        return await start_structured_mode(update, context)
    elif "file" in text.lower():
        return await start_file_mode(update, context)

    # Show mode selection
    await update.message.reply_text(
        "🎬 **Neuer Job**\n\nWähle einen Modus:",
        parse_mode="Markdown",
        reply_markup=get_mode_selection_keyboard(),
    )

    return ConvState.SELECTING_MODE.value


async def mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle mode selection callback."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()

    data = query.data or ""
    mode = data.split(":")[1] if ":" in data else ""

    if mode == "brief":
        return await start_brief_mode(update, context)
    elif mode == "structured":
        return await start_structured_mode(update, context)
    elif mode == "file":
        return await start_file_mode(update, context)

    return ConversationHandler.END


async def start_brief_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start brief mode - AI generates script from description."""
    message = update.callback_query.message if update.callback_query else update.message
    if message is None:
        return ConversationHandler.END

    await message.reply_text(
        "📝 **Brief-Modus**\n\n"
        "Beschreibe dein Briefing. Sag mir:\n"
        "- Was soll die Ad bewerben?\n"
        "- Wer ist die Zielgruppe?\n"
        "- Was ist die Kernbotschaft?\n\n"
        "Beispiel: _Software für Maschinenwartung. Zielgruppe: KMU-Geschäftsführer. "
        "Kernbotschaft: Digitalisierung ist kein Luxus mehr._",
        parse_mode="Markdown",
    )

    return ConvState.AWAITING_BRIEFING.value


async def handle_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle briefing text input."""
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else user_id
    briefing = update.message.text or ""

    if len(briefing) < 20:
        await update.message.reply_text(
            "⚠️ Das Briefing ist zu kurz. Bitte beschreibe ausführlicher."
        )
        return ConvState.AWAITING_BRIEFING.value

    logger.info("Briefing received", user_id=user_id, briefing_length=len(briefing))

    # Create job and generate script
    status_msg = await update.message.reply_text("🤖 Generiere Skript...")

    async with get_session_context() as session:
        # Create job
        job = await crud.create_job(
            session=session,
            telegram_user_id=user_id,
            telegram_chat_id=chat_id,
            briefing=briefing,
            mode=JobMode.BRIEF,
        )

        # Store job ID in context
        context.user_data["current_job_id"] = job.id

        # Update status
        await crud.update_job_status(session, job.id, JobStatus.SCRIPT_GENERATING)

        try:
            # Generate script
            request = ScriptGenerationRequest(briefing=briefing)
            script = await generate_script(request)

            # Create scenes
            for scene_script in script.scenes:
                await crud.create_scene(
                    session=session,
                    job_id=job.id,
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
                job.id,
                title=script.title,
                total_duration_sec=script.total_duration_sec,
                status=JobStatus.SCRIPT_PENDING_REVIEW.value,
            )

            # Show script for review
            await status_msg.edit_text(
                format_script_for_display(script),
                parse_mode="Markdown",
                reply_markup=get_script_review_keyboard(job.id),
            )

        except Exception as e:
            logger.error("Script generation failed", job_id=job.id, error=str(e))
            await crud.update_job_status(
                session, job.id, JobStatus.FAILED, error_message=str(e)
            )
            await status_msg.edit_text(f"❌ Skript-Generierung fehlgeschlagen: {e}")
            return ConversationHandler.END

    return ConversationHandler.END


async def start_file_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start file mode - user uploads YAML script."""
    message = update.callback_query.message if update.callback_query else update.message
    if message is None:
        return ConversationHandler.END

    await message.reply_text(
        "📄 **Datei-Modus**\n\n"
        "Lade ein YAML-Skript hoch. Format:\n\n"
        "```yaml\n"
        "title: \"Mein Video\"\n"
        "scenes:\n"
        "  - order: 1\n"
        "    duration: 5\n"
        "    location: warehouse_modern\n"
        "    camera: selfie_pov_arm_visible\n"
        "    action: talking_to_camera_confident\n"
        "    voiceover: \"POV: Du leitest...\"\n"
        "    lipsync: true\n"
        "```",
        parse_mode="Markdown",
    )

    return ConvState.AWAITING_FILE.value


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle YAML file upload."""
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else user_id

    document = update.message.document
    if document is None:
        # Maybe it's text pasted as YAML
        text = update.message.text
        if text and text.strip().startswith("title:"):
            yaml_content = text
        else:
            await update.message.reply_text("⚠️ Bitte lade eine YAML-Datei hoch.")
            return ConvState.AWAITING_FILE.value
    else:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        yaml_content = file_bytes.decode("utf-8")

    # Parse YAML
    try:
        script = parse_yaml_script(yaml_content)
    except Exception as e:
        await update.message.reply_text(f"❌ YAML-Parsing fehlgeschlagen: {e}")
        return ConvState.AWAITING_FILE.value

    logger.info("YAML script parsed", user_id=user_id, scenes=len(script.scenes))

    async with get_session_context() as session:
        # Create job
        job = await crud.create_job(
            session=session,
            telegram_user_id=user_id,
            telegram_chat_id=chat_id,
            briefing=f"[YAML Upload] {script.title}",
            mode=JobMode.FILE,
        )

        context.user_data["current_job_id"] = job.id

        # Create scenes
        for scene_script in script.scenes:
            await crud.create_scene(
                session=session,
                job_id=job.id,
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
            job.id,
            title=script.title,
            total_duration_sec=script.total_duration_sec,
            status=JobStatus.SCRIPT_PENDING_REVIEW.value,
        )

        # Show for review
        await update.message.reply_text(
            format_script_for_display(script),
            parse_mode="Markdown",
            reply_markup=get_script_review_keyboard(job.id),
        )

    return ConversationHandler.END


async def start_structured_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start structured mode - step by step scene creation."""
    message = update.callback_query.message if update.callback_query else update.message
    if message is None:
        return ConversationHandler.END

    user_id = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id if update.effective_chat else user_id

    # Initialize structured mode data
    context.user_data["structured_scenes"] = []
    context.user_data["current_scene"] = {}

    async with get_session_context() as session:
        job = await crud.create_job(
            session=session,
            telegram_user_id=user_id,
            telegram_chat_id=chat_id,
            briefing="[Structured Mode]",
            mode=JobMode.STRUCTURED,
        )
        context.user_data["current_job_id"] = job.id

    await message.reply_text(
        "🔧 **Strukturierter Modus**\n\n"
        "Wie viele Szenen soll das Video haben? (3-10)",
        parse_mode="Markdown",
    )

    return ConvState.STRUCTURED_SCENE_COUNT.value


async def handle_scene_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle scene count input."""
    if update.message is None:
        return ConversationHandler.END

    text = update.message.text or ""

    try:
        count = int(text.strip())
        if not 3 <= count <= 10:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("⚠️ Bitte gib eine Zahl zwischen 3 und 10 ein.")
        return ConvState.STRUCTURED_SCENE_COUNT.value

    context.user_data["target_scene_count"] = count
    context.user_data["current_scene_num"] = 1

    job_id = context.user_data.get("current_job_id", "")

    await update.message.reply_text(
        f"✅ {count} Szenen\n\n"
        f"**Szene 1** — Wo spielt sie?",
        parse_mode="Markdown",
        reply_markup=get_location_keyboard(job_id),
    )

    return ConvState.STRUCTURED_LOCATION.value


async def handle_location_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle location selection in structured mode."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return ConversationHandler.END

    job_id = parts[1]
    location_key = parts[2]

    context.user_data["current_scene"]["location_key"] = location_key

    await query.message.edit_text(
        f"📍 Location: {location_key.replace('_', ' ').title()}\n\n"
        "**Kamera-Stil?**",
        parse_mode="Markdown",
        reply_markup=get_camera_keyboard(job_id),
    )

    return ConvState.STRUCTURED_CAMERA.value


async def handle_camera_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle camera selection in structured mode."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return ConversationHandler.END

    job_id = parts[1]
    camera_key = parts[2]

    context.user_data["current_scene"]["camera_key"] = camera_key

    await query.message.edit_text(
        f"📍 Location: {context.user_data['current_scene']['location_key'].replace('_', ' ').title()}\n"
        f"📷 Kamera: {camera_key.replace('_', ' ').title()}\n\n"
        "**Was macht die Person?**",
        parse_mode="Markdown",
        reply_markup=get_action_keyboard(job_id),
    )

    return ConvState.STRUCTURED_ACTION.value


async def handle_action_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle action selection in structured mode."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return ConversationHandler.END

    action_key = parts[2]

    context.user_data["current_scene"]["action_key"] = action_key

    await query.message.edit_text(
        f"📍 Location: {context.user_data['current_scene']['location_key'].replace('_', ' ').title()}\n"
        f"📷 Kamera: {context.user_data['current_scene']['camera_key'].replace('_', ' ').title()}\n"
        f"🎬 Action: {action_key.replace('_', ' ').title()}\n\n"
        "**Voiceover-Text (Deutsch)?**\n"
        "Schreibe den Text, den die Person sagen soll:",
        parse_mode="Markdown",
    )

    return ConvState.STRUCTURED_VOICEOVER.value


async def handle_voiceover_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle voiceover text input in structured mode."""
    if update.message is None:
        return ConversationHandler.END

    voiceover = update.message.text or ""
    job_id = context.user_data.get("current_job_id", "")

    context.user_data["current_scene"]["voiceover_de"] = voiceover

    await update.message.reply_text(
        f"🎙 Voiceover: \"{voiceover[:50]}...\"\n\n"
        "**Lipsync aktivieren?**",
        parse_mode="Markdown",
        reply_markup=get_lipsync_keyboard(job_id),
    )

    return ConvState.STRUCTURED_LIPSYNC.value


async def handle_lipsync_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle lipsync selection in structured mode."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    needs_lipsync = parts[2] == "yes" if len(parts) > 2 else True

    job_id = context.user_data.get("current_job_id", "")

    # Complete current scene
    scene_num = context.user_data.get("current_scene_num", 1)
    current_scene = context.user_data.get("current_scene", {})
    current_scene["order"] = scene_num
    current_scene["needs_lipsync"] = needs_lipsync
    current_scene["duration_sec"] = 5.0  # Default duration

    # Add to scenes list
    scenes = context.user_data.get("structured_scenes", [])
    scenes.append(current_scene)
    context.user_data["structured_scenes"] = scenes

    # Reset current scene
    context.user_data["current_scene"] = {}
    context.user_data["current_scene_num"] = scene_num + 1

    target_count = context.user_data.get("target_scene_count", 5)

    if scene_num >= target_count:
        # All scenes collected, finish
        return await finish_structured_script(query, context)

    await query.message.edit_text(
        f"✅ Szene {scene_num} erstellt\n\n"
        f"**Szene {scene_num + 1}** — Wo spielt sie?",
        parse_mode="Markdown",
        reply_markup=get_location_keyboard(job_id),
    )

    return ConvState.STRUCTURED_LOCATION.value


async def finish_structured_script(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finish structured mode and create script."""
    job_id = context.user_data.get("current_job_id", "")
    scenes = context.user_data.get("structured_scenes", [])

    if not scenes:
        await query.message.edit_text("❌ Keine Szenen erstellt.")
        return ConversationHandler.END

    async with get_session_context() as session:
        job = await crud.get_job(session, job_id)
        if job is None:
            await query.message.edit_text("❌ Job nicht gefunden.")
            return ConversationHandler.END

        # Create scenes in database
        total_duration = 0
        for scene_data in scenes:
            await crud.create_scene(
                session=session,
                job_id=job_id,
                order=scene_data["order"],
                duration_sec=scene_data.get("duration_sec", 5.0),
                location_key=scene_data.get("location_key", "warehouse_modern"),
                location_prompt="",
                camera_key=scene_data.get("camera_key", "selfie_pov_arm_visible"),
                action_key=scene_data.get("action_key", "talking_to_camera_confident"),
                voiceover_de=scene_data.get("voiceover_de", ""),
                needs_lipsync=scene_data.get("needs_lipsync", True),
            )
            total_duration += scene_data.get("duration_sec", 5.0)

        # Update job
        await crud.update_job(
            session,
            job_id,
            title="Strukturiertes Video",
            total_duration_sec=total_duration,
            status=JobStatus.SCRIPT_PENDING_REVIEW.value,
        )

        # Refresh job
        job = await crud.get_job(session, job_id)

        # Build script for display
        script = Script(
            title="Strukturiertes Video",
            total_duration_sec=total_duration,
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

    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation."""
    if update.message:
        await update.message.reply_text("❌ Abgebrochen.")
    return ConversationHandler.END


def get_new_job_handler() -> ConversationHandler:
    """Build the conversation handler for /new command."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("new", new_command),
        ],
        states={
            ConvState.SELECTING_MODE.value: [
                CallbackQueryHandler(mode_selected, pattern=r"^mode:"),
            ],
            ConvState.AWAITING_BRIEFING.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_briefing),
            ],
            ConvState.AWAITING_FILE.value: [
                MessageHandler(filters.Document.ALL, handle_file_upload),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_file_upload),
            ],
            ConvState.STRUCTURED_SCENE_COUNT.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_scene_count),
            ],
            ConvState.STRUCTURED_LOCATION.value: [
                CallbackQueryHandler(handle_location_selection, pattern=r"^loc:"),
            ],
            ConvState.STRUCTURED_CAMERA.value: [
                CallbackQueryHandler(handle_camera_selection, pattern=r"^cam:"),
            ],
            ConvState.STRUCTURED_ACTION.value: [
                CallbackQueryHandler(handle_action_selection, pattern=r"^act:"),
            ],
            ConvState.STRUCTURED_VOICEOVER.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_voiceover_input),
            ],
            ConvState.STRUCTURED_LIPSYNC.value: [
                CallbackQueryHandler(handle_lipsync_selection, pattern=r"^lipsync:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^cancel:"),
        ],
        allow_reentry=True,
    )
