"""Command-line interface for AI Storytelling."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Sequence

from storytelling.config import Settings, load_settings
from storytelling.db import REQUIRED_TABLES, DatabaseManager
from storytelling.logging_utils import configure_logging


def run_doctor(settings: Settings) -> dict[str, object]:
    """Perform a non-destructive environment and configuration check."""
    ffmpeg_path = shutil.which(settings.ffmpeg_executable)
    ffprobe_path = shutil.which(settings.ffprobe_executable)
    piper_path = shutil.which(settings.piper_executable)
    models_dir = settings.comfyui_shared_models_dir / "checkpoints"
    checkpoints = (
        [
            p.name
            for p in models_dir.glob("*")
            if p.is_file() and p.suffix.lower() in {".safetensors", ".ckpt"}
        ]
        if models_dir.exists()
        else []
    )
    return {
        "python_version": sys.version.split()[0],
        "llm_provider": settings.llm_provider.value,
        "allow_paid_apis": settings.allow_paid_apis,
        "allow_gemini_api": settings.allow_gemini_api,
        "publishing_enabled": settings.publishing_enabled,
        "max_concurrent_gpu_jobs": settings.max_concurrent_gpu_jobs,
        "ffmpeg_available": bool(ffmpeg_path),
        "ffprobe_available": bool(ffprobe_path),
        "piper_available": bool(piper_path),
        "comfyui_checkpoints_found": len(checkpoints),
        "comfyui_checkpoints": checkpoints,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="storytelling",
        description="Local-first dark mystery storytelling pipeline CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "doctor", help="Run non-destructive environment and config audit"
    )

    db_parser = subparsers.add_parser("db", help="Manage SQLite database")
    db_sub = db_parser.add_subparsers(dest="db_command", required=True)

    init_p = db_sub.add_parser("init", help="Apply SQLite schema migrations")
    init_p.add_argument("--db-path", type=Path, default=None)

    status_p = db_sub.add_parser("status", help="Inspect database migration status")
    status_p.add_argument("--db-path", type=Path, default=None)

    backup_p = db_sub.add_parser("backup", help="Backup SQLite database")
    backup_p.add_argument("--db-path", type=Path, default=None)
    backup_p.add_argument("--output", type=Path, required=True)

    restore_p = db_sub.add_parser("restore", help="Restore SQLite database from backup")
    restore_p.add_argument("--db-path", type=Path, default=None)
    restore_p.add_argument("--input", type=Path, required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()
    configure_logging(settings.log_level)

    if args.command == "doctor":
        report = run_doctor(settings)
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "db":
        db_path = args.db_path or settings.db_path
        db = DatabaseManager(db_path=db_path)

        if args.db_command == "init":
            applied = db.apply_migrations()
            tables = sorted(db.list_tables())
            print(
                json.dumps(
                    {
                        "db_path": str(db.db_path),
                        "applied_now": applied,
                        "all_migrations": db.applied_migrations(),
                        "tables": tables,
                        "required_tables_present": all(
                            t in tables for t in REQUIRED_TABLES
                        ),
                    },
                    indent=2,
                )
            )
            return 0

        if args.db_command == "status":
            tables = sorted(db.list_tables()) if db.db_path.exists() else []
            print(
                json.dumps(
                    {
                        "db_path": str(db.db_path),
                        "exists": db.db_path.exists(),
                        "applied_migrations": db.applied_migrations(),
                        "tables": tables,
                    },
                    indent=2,
                )
            )
            return 0

        if args.db_command == "backup":
            out = db.backup_to(args.output)
            print(json.dumps({"backup_created": str(out)}, indent=2))
            return 0

        if args.db_command == "restore":
            restored = db.restore_from(args.input)
            print(json.dumps({"restored_to": str(restored)}, indent=2))
            return 0

    return 1
