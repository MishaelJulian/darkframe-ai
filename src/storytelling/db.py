"""SQLite database management, migrations, backup/restore, and state transitions."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from storytelling.models import (
    EpisodeRecord,
    JobRecord,
    JobStatus,
    StoryRecord,
    StoryState,
    utc_now_iso,
    validate_state_transition,
)

REQUIRED_TABLES: tuple[str, ...] = (
    "stories",
    "sources",
    "claims",
    "claim_sources",
    "episodes",
    "scenes",
    "assets",
    "jobs",
    "quality_checks",
    "publish_records",
)


class GPUConcurrencyError(RuntimeError):
    """Raised when starting a GPU job while another GPU job is already RUNNING."""


class DatabaseManager:
    """Manages local SQLite connection with WAL mode, foreign keys, and migrations."""

    def __init__(self, db_path: Path, migrations_dir: Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.migrations_dir = (
            Path(migrations_dir)
            if migrations_dir is not None
            else Path(__file__).resolve().parent / "migrations"
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a SQLite connection configured with WAL mode and foreign keys."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def apply_migrations(self) -> list[str]:
        """Apply any unapplied SQL migrations in lexicographical order."""
        applied_now: list[str] = []
        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )
            existing = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations;")
            }
            for sql_file in migration_files:
                version = sql_file.name
                if version in existing:
                    continue
                sql_script = sql_file.read_text(encoding="utf-8")
                conn.executescript(sql_script)
                # Ensure foreign_keys remains ON after executescript
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?);",
                    (version, utc_now_iso()),
                )
                applied_now.append(version)
        return applied_now

    def applied_migrations(self) -> list[str]:
        """Return list of applied migration filenames."""
        if not self.db_path.exists():
            return []
        with self.connect() as conn:
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
            ).fetchone()
            if not table_check:
                return []
            rows = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version;"
            ).fetchall()
            return [str(r["version"]) for r in rows]

    def list_tables(self) -> set[str]:
        """Return set of user tables currently present in the database."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            ).fetchall()
            return {str(r["name"]) for r in rows}

    def backup_to(self, backup_path: Path) -> Path:
        """Create a consistent online backup of the SQLite database."""
        target = Path(backup_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as src_conn:
            with sqlite3.connect(str(target)) as dst_conn:
                src_conn.backup(dst_conn)
        return target

    def restore_from(self, backup_path: Path) -> Path:
        """Restore the database from a backup file."""
        source = Path(backup_path)
        if not source.exists():
            raise FileNotFoundError(f"Backup file not found: {source}")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(source)) as src_conn:
            with sqlite3.connect(str(self.db_path)) as dst_conn:
                src_conn.backup(dst_conn)
        return self.db_path

    def upsert_story(self, story: StoryRecord) -> StoryRecord:
        """Insert a story or return existing record idempotently."""
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM stories WHERE story_id = ?;", (story.story_id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO stories (
                        story_id, title, event_key, event_date, location,
                        sensitive_flag, status, confidence, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        story.story_id,
                        story.title,
                        story.event_key,
                        story.event_date,
                        story.location,
                        int(story.sensitive_flag),
                        story.status.value,
                        story.confidence,
                        story.created_at,
                        story.updated_at,
                    ),
                )
                return story
            return self.get_story(story.story_id)

    def get_story(self, story_id: str) -> StoryRecord:
        """Fetch a story by ID."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM stories WHERE story_id = ?;", (story_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Story not found: {story_id}")
            return StoryRecord(
                story_id=row["story_id"],
                title=row["title"],
                event_key=row["event_key"],
                event_date=row["event_date"],
                location=row["location"],
                sensitive_flag=bool(row["sensitive_flag"]),
                status=StoryState(row["status"]),
                confidence=float(row["confidence"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def transition_story_state(
        self, story_id: str, target_state: StoryState
    ) -> tuple[StoryRecord, bool]:
        """Transition a story's state idempotently, rejecting invalid transitions.

        Returns:
            Tuple of (updated StoryRecord, changed: bool).
        """
        current = self.get_story(story_id)
        changed = validate_state_transition(current.status, target_state)
        if not changed:
            return current, False

        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "UPDATE stories SET status = ?, updated_at = ? WHERE story_id = ?;",
                (target_state.value, now, story_id),
            )
        return self.get_story(story_id), True

    def upsert_episode(self, episode: EpisodeRecord) -> EpisodeRecord:
        """Insert an episode record idempotently."""
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM episodes WHERE episode_id = ?;", (episode.episode_id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO episodes (
                        episode_id, story_id, series_index, title, status,
                        target_duration_sec, actual_duration_sec, word_count,
                        script_json, artifact_hash, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        episode.episode_id,
                        episode.story_id,
                        episode.series_index,
                        episode.title,
                        episode.status.value,
                        episode.target_duration_sec,
                        episode.actual_duration_sec,
                        episode.word_count,
                        None,
                        episode.artifact_hash,
                        episode.created_at,
                        episode.updated_at,
                    ),
                )
        return episode

    def register_job(self, job: JobRecord) -> JobRecord:
        """Register a job idempotently by `job_key`."""
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM jobs WHERE job_key = ?;", (job.job_key,)
            ).fetchone()
            if existing is not None:
                return JobRecord(
                    job_id=existing["job_id"],
                    job_key=existing["job_key"],
                    story_id=existing["story_id"],
                    episode_id=existing["episode_id"],
                    stage=existing["stage"],
                    status=JobStatus(existing["status"]),
                    attempt_count=int(existing["attempt_count"]),
                    max_attempts=int(existing["max_attempts"]),
                    uses_gpu=bool(existing["uses_gpu"]),
                    gpu_seconds=float(existing["gpu_seconds"]),
                    spend_inr=float(existing["spend_inr"]),
                    last_error=existing["last_error"],
                    created_at=existing["created_at"],
                    updated_at=existing["updated_at"],
                )
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, job_key, story_id, episode_id, stage, status,
                    attempt_count, max_attempts, uses_gpu, gpu_seconds,
                    spend_inr, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job.job_id,
                    job.job_key,
                    job.story_id,
                    job.episode_id,
                    job.stage,
                    job.status.value,
                    job.attempt_count,
                    job.max_attempts,
                    int(job.uses_gpu),
                    job.gpu_seconds,
                    job.spend_inr,
                    job.last_error,
                    job.created_at,
                    job.updated_at,
                ),
            )
            return job

    def start_job(self, job_key: str) -> JobRecord:
        """Transition a job to RUNNING, enforcing single-GPU concurrency and max attempts."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_key = ?;", (job_key,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Job not found for key: {job_key}")

            status = JobStatus(row["status"])
            if status == JobStatus.RUNNING:
                return self.register_job(
                    JobRecord(
                        job_id=row["job_id"],
                        job_key=row["job_key"],
                        stage=row["stage"],
                    )
                )
            if status == JobStatus.SUCCEEDED:
                raise ValueError(f"Job {job_key} has already SUCCEEDED.")

            attempts = int(row["attempt_count"])
            max_attempts = int(row["max_attempts"])
            if attempts >= max_attempts:
                raise RuntimeError(
                    f"Job {job_key} exceeded max attempts ({attempts}/{max_attempts})."
                )

            if bool(row["uses_gpu"]):
                active_gpu = conn.execute(
                    "SELECT job_key FROM jobs WHERE uses_gpu = 1 AND status = 'RUNNING' AND job_key != ?;",
                    (job_key,),
                ).fetchone()
                if active_gpu is not None:
                    raise GPUConcurrencyError(
                        f"Cannot start GPU job '{job_key}': GPU is locked by '{active_gpu['job_key']}'."
                    )

            now = utc_now_iso()
            conn.execute(
                """
                UPDATE jobs
                SET status = 'RUNNING', attempt_count = attempt_count + 1, updated_at = ?
                WHERE job_key = ?;
                """,
                (now, job_key),
            )
        return self.register_job(
            JobRecord(job_id=row["job_id"], job_key=job_key, stage=row["stage"])
        )
