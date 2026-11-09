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
from storytelling.image_gen import (
    ComfyUIError,
    ComfyUIClient,
    ImageGenerationRequest,
    LocalImageGenerator,
)
from storytelling.logging_utils import configure_logging
from storytelling.models import EpisodeRecord, StoryRecord


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

    img_parser = subparsers.add_parser(
        "image", help="Local ComfyUI dark 2D image generation"
    )
    img_sub = img_parser.add_subparsers(dest="image_command", required=True)

    img_sub.add_parser(
        "check", help="Check local ComfyUI HTTP API status and installed checkpoints"
    )

    gen_p = img_sub.add_parser(
        "generate", help="Generate a dark 2D vertical scene illustration via ComfyUI"
    )
    gen_p.add_argument("--prompt", type=str, required=True)
    gen_p.add_argument("--episode-id", type=str, default="ep_m2_proof")
    gen_p.add_argument("--scene-index", type=int, default=0)
    gen_p.add_argument("--seed", type=int, default=42)
    gen_p.add_argument("--width", type=int, default=512)
    gen_p.add_argument("--height", type=int, default=768)
    gen_p.add_argument("--steps", type=int, default=24)
    gen_p.add_argument("--checkpoint", type=str, default=None)
    gen_p.add_argument("--license-id", type=str, default="creativeml-openrail-m")
    gen_p.add_argument("--db-path", type=Path, default=None)
    gen_p.add_argument("--output-dir", type=Path, default=None)

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

    if args.command == "image":
        client = ComfyUIClient(settings=settings)
        if args.image_command == "check":
            try:
                base_url = client.detect_base_url()
                checkpoints = client.list_checkpoints()
                print(
                    json.dumps(
                        {
                            "comfyui_reachable": True,
                            "base_url": base_url,
                            "checkpoints": checkpoints,
                        },
                        indent=2,
                    )
                )
                return 0
            except ComfyUIError as exc:
                print(
                    json.dumps(
                        {
                            "comfyui_reachable": False,
                            "error": str(exc),
                        },
                        indent=2,
                    )
                )
                return 1

        if args.image_command == "generate":
            db_path = args.db_path or settings.db_path
            db = DatabaseManager(db_path=db_path)
            db.apply_migrations()
            story_id = f"story_for_{args.episode_id}"
            db.upsert_story(
                StoryRecord(
                    story_id=story_id,
                    title=f"Story for {args.episode_id}",
                    event_key=f"event-{args.episode_id}",
                )
            )
            db.upsert_episode(
                EpisodeRecord(
                    episode_id=args.episode_id,
                    story_id=story_id,
                    series_index=1,
                    title=f"Episode {args.episode_id}",
                )
            )
            generator = LocalImageGenerator(settings=settings, db=db, client=client)
            req = ImageGenerationRequest(
                episode_id=args.episode_id,
                scene_index=args.scene_index,
                visual_prompt=args.prompt,
                checkpoint_name=args.checkpoint,
                license_id=args.license_id,
                seed=args.seed,
                width=args.width,
                height=args.height,
                steps=args.steps,
            )
            result = generator.generate_scene_image(
                req, output_dir=args.output_dir
            )
            print(result.model_dump_json(indent=2))
            return 0

    return 1
