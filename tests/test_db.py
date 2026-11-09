"""Tests for SQLite migrations, WAL mode, foreign keys, backup/restore, and jobs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from storytelling.db import GPUConcurrencyError, REQUIRED_TABLES, DatabaseManager
from storytelling.models import (
    EpisodeRecord,
    InvalidStateTransitionError,
    JobRecord,
    JobStatus,
    StoryRecord,
    StoryState,
)


def test_migrations_create_all_required_tables_and_wal_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "test_storytelling.db"
    db = DatabaseManager(db_path)

    first_run = db.apply_migrations()
    assert first_run == ["001_initial.sql"]

    # Idempotent second run
    second_run = db.apply_migrations()
    assert second_run == []

    tables = db.list_tables()
    for required in REQUIRED_TABLES:
        assert required in tables

    with db.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        fk_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert str(journal_mode).lower() == "wal"
        assert fk_enabled == 1


def test_foreign_key_constraints_enforced(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "fk_test.db")
    db.apply_migrations()

    # Inserting an episode referencing a non-existent story_id must fail
    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_episode(
            EpisodeRecord(
                episode_id="ep_orphan",
                story_id="non_existent_story",
                series_index=1,
                title="Orphan Episode",
            )
        )


def test_story_state_transitions_are_idempotent_and_reject_invalid(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "states.db")
    db.apply_migrations()

    story = StoryRecord(
        story_id="st_flannan",
        title="The Flannan Isles Lighthouse Disappearance",
        event_key="1900-12-flannan-isles-lighthouse",
        event_date="1900-12-15",
        location="Outer Hebrides, Scotland",
        confidence=0.95,
    )
    db.upsert_story(story)

    # Idempotent self-transition returns changed=False
    same_story, changed = db.transition_story_state("st_flannan", StoryState.DISCOVERED)
    assert changed is False
    assert same_story.status == StoryState.DISCOVERED

    # Valid transition to RESEARCHING
    updated, changed = db.transition_story_state("st_flannan", StoryState.RESEARCHING)
    assert changed is True
    assert updated.status == StoryState.RESEARCHING

    # Repeat transition to RESEARCHING is idempotent
    updated_again, changed_again = db.transition_story_state(
        "st_flannan", StoryState.RESEARCHING
    )
    assert changed_again is False
    assert updated_again.status == StoryState.RESEARCHING

    # Invalid transition directly to PUBLISHED must fail
    with pytest.raises(InvalidStateTransitionError):
        db.transition_story_state("st_flannan", StoryState.PUBLISHED)


def test_gpu_job_concurrency_lock_and_idempotency(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "jobs.db")
    db.apply_migrations()

    job1 = JobRecord(
        job_id="job_1",
        job_key="ep1:image:scene1",
        stage="IMAGE_GENERATION",
        uses_gpu=True,
    )
    job2 = JobRecord(
        job_id="job_2",
        job_key="ep1:image:scene2",
        stage="IMAGE_GENERATION",
        uses_gpu=True,
    )
    # Registering same job_key twice is idempotent
    db.register_job(job1)
    duplicate = db.register_job(
        JobRecord(
            job_id="job_1_dup",
            job_key="ep1:image:scene1",
            stage="IMAGE_GENERATION",
            uses_gpu=True,
        )
    )
    assert duplicate.job_id == "job_1"

    db.register_job(job2)

    started1 = db.start_job("ep1:image:scene1")
    assert started1.status == JobStatus.RUNNING
    assert started1.attempt_count == 1

    # Starting a second GPU job while job1 is RUNNING must raise GPUConcurrencyError
    with pytest.raises(GPUConcurrencyError):
        db.start_job("ep1:image:scene2")


def test_database_backup_and_restore(tmp_path: Path) -> None:
    orig_db_path = tmp_path / "orig" / "storytelling.db"
    backup_path = tmp_path / "backups" / "storytelling_backup.db"
    restored_db_path = tmp_path / "restored" / "storytelling.db"

    db = DatabaseManager(orig_db_path)
    db.apply_migrations()
    db.upsert_story(
        StoryRecord(
            story_id="st_backup_test",
            title="Backup Test Mystery",
            event_key="backup-test-event",
        )
    )

    db.backup_to(backup_path)
    assert backup_path.exists()

    restored_db = DatabaseManager(restored_db_path)
    restored_db.restore_from(backup_path)
    fetched = restored_db.get_story("st_backup_test")
    assert fetched.title == "Backup Test Mystery"
