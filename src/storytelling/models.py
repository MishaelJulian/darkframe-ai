"""Domain models, state machine contracts, and transition validators."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class StoryState(StrEnum):
    """Persistent pipeline state machine defined in specs/08-AUTOMATION.md."""

    DISCOVERED = "DISCOVERED"
    RESEARCHING = "RESEARCHING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    SCRIPTED = "SCRIPTED"
    ASSETS_READY = "ASSETS_READY"
    RENDERED = "RENDERED"
    QC_PASSED = "QC_PASSED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ClaimStatus(StrEnum):
    """Verification status for factual claims (specs/03-RESEARCH-VERIFICATION.md)."""

    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    UNVERIFIED = "UNVERIFIED"


class QCStatus(StrEnum):
    """Quality control gate outcome (specs/10-QUALITY-CONTROL.md)."""

    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class JobStatus(StrEnum):
    """Execution status of an individual pipeline job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


class AssetType(StrEnum):
    """Generated or sourced media asset types."""

    IMAGE = "IMAGE"
    AUDIO_NARRATION = "AUDIO_NARRATION"
    AUDIO_AMBIENT = "AUDIO_AMBIENT"
    SUBTITLE = "SUBTITLE"
    VIDEO_MP4 = "VIDEO_MP4"
    MANIFEST = "MANIFEST"


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is requested."""


# Directed graph of valid state transitions (excluding self-transitions, which are idempotent)
VALID_STATE_TRANSITIONS: dict[StoryState, frozenset[StoryState]] = {
    StoryState.DISCOVERED: frozenset({StoryState.RESEARCHING, StoryState.FAILED}),
    StoryState.RESEARCHING: frozenset(
        {StoryState.NEEDS_REVIEW, StoryState.APPROVED, StoryState.FAILED}
    ),
    StoryState.NEEDS_REVIEW: frozenset(
        {StoryState.APPROVED, StoryState.RESEARCHING, StoryState.FAILED}
    ),
    StoryState.APPROVED: frozenset(
        {StoryState.SCRIPTED, StoryState.NEEDS_REVIEW, StoryState.FAILED}
    ),
    StoryState.SCRIPTED: frozenset(
        {StoryState.ASSETS_READY, StoryState.NEEDS_REVIEW, StoryState.FAILED}
    ),
    StoryState.ASSETS_READY: frozenset(
        {StoryState.RENDERED, StoryState.SCRIPTED, StoryState.FAILED}
    ),
    StoryState.RENDERED: frozenset(
        {
            StoryState.QC_PASSED,
            StoryState.NEEDS_REVIEW,
            StoryState.ASSETS_READY,
            StoryState.FAILED,
        }
    ),
    StoryState.QC_PASSED: frozenset(
        {StoryState.PUBLISHED, StoryState.NEEDS_REVIEW, StoryState.FAILED}
    ),
    StoryState.PUBLISHED: frozenset(),
    # FAILED can be recovered by resetting to a valid prior checkpoint state
    StoryState.FAILED: frozenset(
        {
            StoryState.DISCOVERED,
            StoryState.RESEARCHING,
            StoryState.NEEDS_REVIEW,
            StoryState.APPROVED,
            StoryState.SCRIPTED,
            StoryState.ASSETS_READY,
            StoryState.RENDERED,
        }
    ),
}


def validate_state_transition(current: StoryState, target: StoryState) -> bool:
    """Validate a pipeline state transition.

    Returns:
        False if the transition is an idempotent no-op (current == target).
        True if the transition is a valid state change.

    Raises:
        InvalidStateTransitionError: If the transition from `current` to `target` is forbidden.
    """
    if current == target:
        return False
    allowed = VALID_STATE_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"Illegal state transition from {current.value} to {target.value}. "
            f"Allowed targets: {sorted(s.value for s in allowed)}"
        )
    return True


class StoryRecord(BaseModel):
    """Typed contract for a story entity."""

    model_config = ConfigDict(extra="forbid")

    story_id: str
    title: str
    event_key: str
    event_date: str | None = None
    location: str | None = None
    sensitive_flag: bool = False
    status: StoryState = StoryState.DISCOVERED
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class SourceRecord(BaseModel):
    """Typed contract for a research source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    story_id: str
    url: str
    source_type: str
    title: str | None = None
    published_at: str | None = None
    retrieved_at: str = Field(default_factory=utc_now_iso)
    is_primary: bool = False
    independence_group: str | None = None
    license_notes: str | None = None


class ClaimRecord(BaseModel):
    """Typed contract for a factual claim requiring verification."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    story_id: str
    statement: str
    is_central: bool = True
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    uncertainty_notes: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class EpisodeRecord(BaseModel):
    """Typed contract for a single 60-second episode."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    story_id: str
    series_index: int = Field(default=1, ge=1)
    title: str
    status: StoryState = StoryState.DISCOVERED
    target_duration_sec: float = Field(default=60.0, gt=0.0)
    actual_duration_sec: float | None = None
    word_count: int | None = None
    script_json: dict[str, Any] | None = None
    artifact_hash: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class JobRecord(BaseModel):
    """Typed contract for an idempotent pipeline job."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_key: str
    story_id: str | None = None
    episode_id: str | None = None
    stage: str
    status: JobStatus = JobStatus.PENDING
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    uses_gpu: bool = False
    gpu_seconds: float = Field(default=0.0, ge=0.0)
    spend_inr: float = Field(default=0.0, ge=0.0)
    last_error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class AssetRecord(BaseModel):
    """Typed contract for a generated or sourced media asset (specs/11-DATABASE.md)."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    episode_id: str
    scene_id: str | None = None
    asset_type: AssetType
    file_path: str
    sha256_checksum: str
    byte_size: int = Field(ge=0)
    model_name: str | None = None
    model_version: str | None = None
    license_id: str
    rights_provenance: str
    metadata_json: dict[str, Any] | None = None
    created_at: str = Field(default_factory=utc_now_iso)

