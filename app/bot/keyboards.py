"""Telegram inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import JobStatus


def get_mode_selection_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting job creation mode."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Brief (AI generiert)", callback_data="mode:brief"),
        ],
        [
            InlineKeyboardButton("🔧 Strukturiert", callback_data="mode:structured"),
        ],
        [
            InlineKeyboardButton("📄 Datei Upload", callback_data="mode:file"),
        ],
    ])


def get_script_review_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Keyboard for script review."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Render starten", callback_data=f"approve:{job_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Szene ändern", callback_data=f"edit:{job_id}"),
            InlineKeyboardButton("🔄 Komplett neu", callback_data=f"regenerate:{job_id}"),
        ],
        [
            InlineKeyboardButton("❌ Abbrechen", callback_data=f"cancel:{job_id}"),
        ],
    ])


def get_final_review_keyboard(job_id: str, scene_count: int) -> InlineKeyboardMarkup:
    """Keyboard for final video review."""
    buttons = [
        [
            InlineKeyboardButton("✅ Ship it!", callback_data=f"final_approve:{job_id}"),
        ],
    ]

    # Add re-render buttons for each scene
    if scene_count <= 4:
        scene_buttons = [
            InlineKeyboardButton(f"🔄 S{i}", callback_data=f"rerender:{job_id}:{i}")
            for i in range(1, scene_count + 1)
        ]
        buttons.append(scene_buttons)
    else:
        buttons.append([
            InlineKeyboardButton("🔄 Szene neu rendern", callback_data=f"rerender_select:{job_id}"),
        ])

    buttons.append([
        InlineKeyboardButton("❌ Verwerfen", callback_data=f"cancel:{job_id}"),
    ])

    return InlineKeyboardMarkup(buttons)


def get_cancel_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Keyboard for cancel confirmation."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ja, abbrechen", callback_data=f"confirm_cancel:{job_id}"),
            InlineKeyboardButton("❌ Nein", callback_data=f"keep:{job_id}"),
        ],
    ])


def get_scene_selection_keyboard(job_id: str, scene_count: int) -> InlineKeyboardMarkup:
    """Keyboard for selecting a scene to re-render."""
    buttons = []
    row = []
    for i in range(1, scene_count + 1):
        row.append(InlineKeyboardButton(f"Szene {i}", callback_data=f"rerender:{job_id}:{i}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("« Zurück", callback_data=f"back_to_review:{job_id}"),
    ])

    return InlineKeyboardMarkup(buttons)


def get_location_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Keyboard for selecting a location (structured mode)."""
    from app.services.library import get_library

    library = get_library()
    buttons = []
    row = []

    for key in library.get_location_keys()[:8]:  # Limit to 8 options
        label = key.replace("_", " ").title()
        row.append(InlineKeyboardButton(label, callback_data=f"loc:{job_id}:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("❌ Abbrechen", callback_data=f"cancel:{job_id}"),
    ])

    return InlineKeyboardMarkup(buttons)


def get_camera_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Keyboard for selecting a camera style (structured mode)."""
    from app.services.library import get_library

    library = get_library()
    buttons = []
    row = []

    for key in library.get_camera_keys()[:6]:
        label = key.replace("_", " ").title()[:15]
        row.append(InlineKeyboardButton(label, callback_data=f"cam:{job_id}:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("❌ Abbrechen", callback_data=f"cancel:{job_id}"),
    ])

    return InlineKeyboardMarkup(buttons)


def get_action_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Keyboard for selecting an action (structured mode)."""
    from app.services.library import get_library

    library = get_library()
    buttons = []
    row = []

    for key in library.get_action_keys()[:6]:
        label = key.replace("_", " ").title()[:15]
        row.append(InlineKeyboardButton(label, callback_data=f"act:{job_id}:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("❌ Abbrechen", callback_data=f"cancel:{job_id}"),
    ])

    return InlineKeyboardMarkup(buttons)


def get_lipsync_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Keyboard for lipsync selection."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ja, Lipsync", callback_data=f"lipsync:{job_id}:yes"),
            InlineKeyboardButton("❌ Nein", callback_data=f"lipsync:{job_id}:no"),
        ],
    ])


def get_continue_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Keyboard for continuing to next scene or finishing."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Weitere Szene", callback_data=f"add_scene:{job_id}"),
            InlineKeyboardButton("✅ Fertig", callback_data=f"finish_structured:{job_id}"),
        ],
    ])


def format_status_indicator(status: JobStatus) -> str:
    """Format status with emoji."""
    emoji_map = {
        JobStatus.BRIEFING_RECEIVED: "📝",
        JobStatus.SCRIPT_GENERATING: "🤖",
        JobStatus.SCRIPT_PENDING_REVIEW: "📋",
        JobStatus.SCRIPT_APPROVED: "✅",
        JobStatus.STILLS_SELECTING: "🖼️",
        JobStatus.VIDEO_RENDERING: "🎬",
        JobStatus.AUDIO_RENDERING: "🎙️",
        JobStatus.LIPSYNC_RUNNING: "👄",
        JobStatus.ASSEMBLY_RUNNING: "🔧",
        JobStatus.FINAL_PENDING_REVIEW: "👀",
        JobStatus.COMPLETED: "🎉",
        JobStatus.FAILED: "❌",
        JobStatus.CANCELLED: "🚫",
    }
    return emoji_map.get(status, "❓")
