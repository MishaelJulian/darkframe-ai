"""Tests for domain models and state machine transition validation."""

from __future__ import annotations

import pytest

from storytelling.models import (
    InvalidStateTransitionError,
    StoryState,
    validate_state_transition,
)


def test_idempotent_self_transitions() -> None:
    for state in StoryState:
        assert validate_state_transition(state, state) is False


def test_valid_forward_and_review_transitions() -> None:
    assert validate_state_transition(StoryState.DISCOVERED, StoryState.RESEARCHING) is True
    assert validate_state_transition(StoryState.RESEARCHING, StoryState.NEEDS_REVIEW) is True
    assert validate_state_transition(StoryState.NEEDS_REVIEW, StoryState.APPROVED) is True
    assert validate_state_transition(StoryState.APPROVED, StoryState.SCRIPTED) is True
    assert validate_state_transition(StoryState.SCRIPTED, StoryState.ASSETS_READY) is True
    assert validate_state_transition(StoryState.ASSETS_READY, StoryState.RENDERED) is True
    assert validate_state_transition(StoryState.RENDERED, StoryState.QC_PASSED) is True
    assert validate_state_transition(StoryState.QC_PASSED, StoryState.PUBLISHED) is True


def test_reject_invalid_transitions() -> None:
    with pytest.raises(InvalidStateTransitionError):
        validate_state_transition(StoryState.DISCOVERED, StoryState.PUBLISHED)

    with pytest.raises(InvalidStateTransitionError):
        validate_state_transition(StoryState.RESEARCHING, StoryState.RENDERED)

    with pytest.raises(InvalidStateTransitionError):
        validate_state_transition(StoryState.PUBLISHED, StoryState.SCRIPTED)
