"""Tests for state machine."""

import pytest

from app.db.models import JobStatus
from app.services.state_machine import (
    can_transition,
    validate_transition,
    InvalidTransitionError,
    get_allowed_transitions,
    get_status_description,
    get_status_emoji,
    format_status,
    is_terminal_status,
    is_error_status,
    is_pending_review,
    is_processing,
    get_next_render_status,
)


class TestCanTransition:
    """Tests for can_transition function."""

    def test_valid_transition_from_briefing_to_generating(self):
        assert can_transition(JobStatus.BRIEFING_RECEIVED, JobStatus.SCRIPT_GENERATING) is True

    def test_valid_transition_from_generating_to_review(self):
        assert can_transition(JobStatus.SCRIPT_GENERATING, JobStatus.SCRIPT_PENDING_REVIEW) is True

    def test_valid_transition_to_failed(self):
        assert can_transition(JobStatus.SCRIPT_GENERATING, JobStatus.FAILED) is True
        assert can_transition(JobStatus.VIDEO_RENDERING, JobStatus.FAILED) is True

    def test_invalid_transition_backwards(self):
        assert can_transition(JobStatus.SCRIPT_PENDING_REVIEW, JobStatus.BRIEFING_RECEIVED) is False

    def test_invalid_transition_skip_state(self):
        assert can_transition(JobStatus.BRIEFING_RECEIVED, JobStatus.VIDEO_RENDERING) is False

    def test_completed_is_terminal(self):
        assert can_transition(JobStatus.COMPLETED, JobStatus.BRIEFING_RECEIVED) is False
        assert can_transition(JobStatus.COMPLETED, JobStatus.FAILED) is False

    def test_cancelled_is_terminal(self):
        assert can_transition(JobStatus.CANCELLED, JobStatus.BRIEFING_RECEIVED) is False

    def test_failed_allows_retry(self):
        assert can_transition(JobStatus.FAILED, JobStatus.SCRIPT_GENERATING) is True


class TestValidateTransition:
    """Tests for validate_transition function."""

    def test_valid_transition_no_error(self):
        # Should not raise
        validate_transition(JobStatus.BRIEFING_RECEIVED, JobStatus.SCRIPT_GENERATING)

    def test_invalid_transition_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(JobStatus.COMPLETED, JobStatus.BRIEFING_RECEIVED)

        assert exc_info.value.from_status == JobStatus.COMPLETED
        assert exc_info.value.to_status == JobStatus.BRIEFING_RECEIVED


class TestGetAllowedTransitions:
    """Tests for get_allowed_transitions function."""

    def test_briefing_received_transitions(self):
        allowed = get_allowed_transitions(JobStatus.BRIEFING_RECEIVED)
        assert JobStatus.SCRIPT_GENERATING in allowed
        assert JobStatus.FAILED in allowed
        assert JobStatus.CANCELLED in allowed

    def test_completed_no_transitions(self):
        allowed = get_allowed_transitions(JobStatus.COMPLETED)
        assert allowed == []


class TestStatusHelpers:
    """Tests for status helper functions."""

    def test_get_status_description(self):
        desc = get_status_description(JobStatus.SCRIPT_GENERATING)
        assert "generiert" in desc.lower()

    def test_get_status_emoji(self):
        emoji = get_status_emoji(JobStatus.COMPLETED)
        assert emoji == "🎉"

    def test_format_status(self):
        formatted = format_status(JobStatus.COMPLETED)
        assert "🎉" in formatted
        assert "Abgeschlossen" in formatted


class TestStatusChecks:
    """Tests for status check functions."""

    def test_is_terminal_status(self):
        assert is_terminal_status(JobStatus.COMPLETED) is True
        assert is_terminal_status(JobStatus.CANCELLED) is True
        assert is_terminal_status(JobStatus.FAILED) is False
        assert is_terminal_status(JobStatus.VIDEO_RENDERING) is False

    def test_is_error_status(self):
        assert is_error_status(JobStatus.FAILED) is True
        assert is_error_status(JobStatus.CANCELLED) is False
        assert is_error_status(JobStatus.COMPLETED) is False

    def test_is_pending_review(self):
        assert is_pending_review(JobStatus.SCRIPT_PENDING_REVIEW) is True
        assert is_pending_review(JobStatus.FINAL_PENDING_REVIEW) is True
        assert is_pending_review(JobStatus.VIDEO_RENDERING) is False

    def test_is_processing(self):
        assert is_processing(JobStatus.VIDEO_RENDERING) is True
        assert is_processing(JobStatus.AUDIO_RENDERING) is True
        assert is_processing(JobStatus.LIPSYNC_RUNNING) is True
        assert is_processing(JobStatus.COMPLETED) is False
        assert is_processing(JobStatus.SCRIPT_PENDING_REVIEW) is False


class TestGetNextRenderStatus:
    """Tests for get_next_render_status function."""

    def test_from_approved_to_stills(self):
        next_status = get_next_render_status(JobStatus.SCRIPT_APPROVED)
        assert next_status == JobStatus.STILLS_SELECTING

    def test_from_video_to_audio(self):
        next_status = get_next_render_status(JobStatus.VIDEO_RENDERING)
        assert next_status == JobStatus.AUDIO_RENDERING

    def test_from_assembly_to_review(self):
        next_status = get_next_render_status(JobStatus.ASSEMBLY_RUNNING)
        assert next_status == JobStatus.FINAL_PENDING_REVIEW

    def test_from_review_returns_none(self):
        next_status = get_next_render_status(JobStatus.FINAL_PENDING_REVIEW)
        assert next_status is None

    def test_non_render_status_returns_none(self):
        next_status = get_next_render_status(JobStatus.COMPLETED)
        assert next_status is None
