"""Job state machine implementation."""

from typing import Optional

import structlog

from app.db.models import JobStatus

logger = structlog.get_logger()

# Valid state transitions
TRANSITIONS: dict[JobStatus, list[JobStatus]] = {
    JobStatus.BRIEFING_RECEIVED: [JobStatus.SCRIPT_GENERATING, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.SCRIPT_GENERATING: [JobStatus.SCRIPT_PENDING_REVIEW, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.SCRIPT_PENDING_REVIEW: [
        JobStatus.SCRIPT_APPROVED,
        JobStatus.SCRIPT_GENERATING,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    ],
    JobStatus.SCRIPT_APPROVED: [JobStatus.STILLS_SELECTING, JobStatus.VIDEO_RENDERING, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.STILLS_SELECTING: [JobStatus.VIDEO_RENDERING, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.VIDEO_RENDERING: [JobStatus.AUDIO_RENDERING, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.AUDIO_RENDERING: [JobStatus.LIPSYNC_RUNNING, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.LIPSYNC_RUNNING: [JobStatus.ASSEMBLY_RUNNING, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.ASSEMBLY_RUNNING: [JobStatus.FINAL_PENDING_REVIEW, JobStatus.FAILED, JobStatus.CANCELLED],
    JobStatus.FINAL_PENDING_REVIEW: [
        JobStatus.COMPLETED,
        JobStatus.VIDEO_RENDERING,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    ],
    JobStatus.COMPLETED: [],
    JobStatus.FAILED: [JobStatus.SCRIPT_GENERATING],  # Allow retry from failed
    JobStatus.CANCELLED: [],
}

# Human-readable status descriptions (German)
STATUS_DESCRIPTIONS: dict[JobStatus, str] = {
    JobStatus.BRIEFING_RECEIVED: "Briefing erhalten",
    JobStatus.SCRIPT_GENERATING: "Skript wird generiert...",
    JobStatus.SCRIPT_PENDING_REVIEW: "Skript wartet auf Freigabe",
    JobStatus.SCRIPT_APPROVED: "Skript freigegeben",
    JobStatus.STILLS_SELECTING: "Standbilder werden ausgewählt...",
    JobStatus.VIDEO_RENDERING: "Videos werden gerendert...",
    JobStatus.AUDIO_RENDERING: "Audio wird generiert...",
    JobStatus.LIPSYNC_RUNNING: "Lipsync wird angewendet...",
    JobStatus.ASSEMBLY_RUNNING: "Video wird zusammengestellt...",
    JobStatus.FINAL_PENDING_REVIEW: "Finales Video wartet auf Freigabe",
    JobStatus.COMPLETED: "Abgeschlossen",
    JobStatus.FAILED: "Fehlgeschlagen",
    JobStatus.CANCELLED: "Abgebrochen",
}

# Status emojis
STATUS_EMOJIS: dict[JobStatus, str] = {
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


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_status: JobStatus, to_status: JobStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid transition from {from_status.value} to {to_status.value}"
        )


def can_transition(from_status: JobStatus, to_status: JobStatus) -> bool:
    """Check if a state transition is valid."""
    allowed = TRANSITIONS.get(from_status, [])
    return to_status in allowed


def validate_transition(from_status: JobStatus, to_status: JobStatus) -> None:
    """Validate a state transition, raising an error if invalid."""
    if not can_transition(from_status, to_status):
        raise InvalidTransitionError(from_status, to_status)


def get_allowed_transitions(status: JobStatus) -> list[JobStatus]:
    """Get list of allowed next states from current status."""
    return TRANSITIONS.get(status, [])


def get_status_description(status: JobStatus) -> str:
    """Get human-readable description for status."""
    return STATUS_DESCRIPTIONS.get(status, status.value)


def get_status_emoji(status: JobStatus) -> str:
    """Get emoji for status."""
    return STATUS_EMOJIS.get(status, "❓")


def format_status(status: JobStatus) -> str:
    """Format status with emoji and description."""
    emoji = get_status_emoji(status)
    description = get_status_description(status)
    return f"{emoji} {description}"


def is_terminal_status(status: JobStatus) -> bool:
    """Check if status is terminal (no further transitions possible)."""
    return status in [JobStatus.COMPLETED, JobStatus.CANCELLED]


def is_error_status(status: JobStatus) -> bool:
    """Check if status indicates an error."""
    return status == JobStatus.FAILED


def is_pending_review(status: JobStatus) -> bool:
    """Check if status is waiting for user review."""
    return status in [JobStatus.SCRIPT_PENDING_REVIEW, JobStatus.FINAL_PENDING_REVIEW]


def is_processing(status: JobStatus) -> bool:
    """Check if job is actively being processed."""
    return status in [
        JobStatus.SCRIPT_GENERATING,
        JobStatus.STILLS_SELECTING,
        JobStatus.VIDEO_RENDERING,
        JobStatus.AUDIO_RENDERING,
        JobStatus.LIPSYNC_RUNNING,
        JobStatus.ASSEMBLY_RUNNING,
    ]


def get_next_render_status(current_status: JobStatus) -> Optional[JobStatus]:
    """Get the next status in the render pipeline."""
    pipeline = [
        JobStatus.SCRIPT_APPROVED,
        JobStatus.STILLS_SELECTING,
        JobStatus.VIDEO_RENDERING,
        JobStatus.AUDIO_RENDERING,
        JobStatus.LIPSYNC_RUNNING,
        JobStatus.ASSEMBLY_RUNNING,
        JobStatus.FINAL_PENDING_REVIEW,
    ]

    try:
        idx = pipeline.index(current_status)
        if idx < len(pipeline) - 1:
            return pipeline[idx + 1]
    except ValueError:
        pass

    return None
