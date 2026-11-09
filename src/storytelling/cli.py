"""Command-line interface for AI Storytelling."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Sequence

from storytelling.config import Settings, StylePresetChoice, load_settings
from storytelling.db import REQUIRED_TABLES, DatabaseManager
from storytelling.image_gen import (
    ComfyUIError,
    ComfyUIClient,
    ImageGenerationRequest,
    LocalImageGenerator,
)
from storytelling.logging_utils import configure_logging
from storytelling.models import EpisodeRecord, StoryRecord
from storytelling.subtitles import write_episode_subtitles
from storytelling.video_prod import (
    CameraMotionType,
    LayerRole,
    SceneLayer,
    SceneRenderSpec,
    VideoAssembler,
)
from storytelling.voiceover import NarrationSegmentInput, VoiceoverGenerator


def run_doctor(settings: Settings) -> dict[str, object]:
    """Perform a non-destructive environment and configuration check."""
    ffmpeg_path = shutil.which(settings.ffmpeg_executable)
    ffprobe_path = shutil.which(settings.ffprobe_executable)
    piper_path = shutil.which(settings.piper_executable) or (
        str(Path(settings.piper_executable))
        if Path(settings.piper_executable).exists()
        else None
    )
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
    gen_p.add_argument("--subject", type=str, default=None)
    gen_p.add_argument("--setting", type=str, default=None)
    gen_p.add_argument("--time-of-day", type=str, default=None)
    gen_p.add_argument("--key-object", action="append", default=[])
    gen_p.add_argument("--episode-id", type=str, default="ep_m2_proof")
    gen_p.add_argument("--scene-index", type=int, default=0)
    gen_p.add_argument("--seed", type=int, default=42)
    gen_p.add_argument("--width", type=int, default=512)
    gen_p.add_argument("--height", type=int, default=896)
    gen_p.add_argument("--steps", type=int, default=24)
    gen_p.add_argument(
        "--style-preset",
        type=StylePresetChoice,
        choices=list(StylePresetChoice),
        default=StylePresetChoice.DARK_CINEMATIC_2D,
    )
    gen_p.add_argument("--checkpoint", type=str, default=None)
    gen_p.add_argument("--license-id", type=str, default="other")
    gen_p.add_argument("--db-path", type=Path, default=None)
    gen_p.add_argument("--output-dir", type=Path, default=None)

    vid_parser = subparsers.add_parser(
        "video", help="Local FFmpeg 1080x1920 vertical video production"
    )
    vid_sub = vid_parser.add_subparsers(dest="video_command", required=True)

    poc_p = vid_sub.add_parser(
        "render-poc",
        help="Render the 15-second 1080x1920 proof-of-concept video from two DARK_CINEMATIC_2D scenes",
    )
    poc_p.add_argument("--episode-id", type=str, default="ep_m3_poc")
    poc_p.add_argument(
        "--scene0-image",
        type=Path,
        default=Path(
            "output/ep_dark_cinematic_2d/images/scene_00_DARK_CINEMATIC_2D_512x896_seed_19001215.png"
        ),
    )
    poc_p.add_argument(
        "--scene1-image",
        type=Path,
        default=Path(
            "output/ep_dark_cinematic_2d/images/scene_01_DARK_CINEMATIC_2D_512x896_seed_19001226.png"
        ),
    )
    poc_p.add_argument("--upscale-factor", type=int, choices=[1, 2], default=1)
    poc_p.add_argument(
        "--output-filename", type=str, default="poc_1080x1920_upscale1x.mp4"
    )
    poc_p.add_argument(
        "--tts-engine",
        type=str,
        choices=["piper", "pyttsx3"],
        default=None,
        help="Override TTS engine (default: settings.tts_engine='piper' with SAPI5 fallback)",
    )
    poc_p.add_argument("--db-path", type=Path, default=None)
    poc_p.add_argument("--output-dir", type=Path, default=None)

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
                primary_subject=args.subject,
                setting=args.setting,
                time_of_day=args.time_of_day,
                key_objects=args.key_object or [],
                style_preset=args.style_preset,
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

    if args.command == "video":
        if args.video_command == "render-poc":
            db_path = args.db_path or settings.db_path
            out_root = args.output_dir or settings.output_dir
            db = DatabaseManager(db_path=db_path)
            db.apply_migrations()

            story_id = f"story_for_{args.episode_id}"
            db.upsert_story(
                StoryRecord(
                    story_id=story_id,
                    title="Flannan Isles Lighthouse Disappearance (December 1900 PoC)",
                    event_key=f"flannan-isles-1900-{args.episode_id}",
                )
            )
            db.upsert_episode(
                EpisodeRecord(
                    episode_id=args.episode_id,
                    story_id=story_id,
                    series_index=1,
                    title="Eilean Mor: The Silent Lamp (M3 Proof of Concept)",
                )
            )

            segments_in = [
                NarrationSegmentInput(
                    scene_index=0,
                    text=(
                        "In December nineteen hundred, the relief vessel Hesperus reached "
                        "the isolated lighthouse on Eilean Mor in the Outer Hebrides."
                    ),
                    pause_after_sec=0.45,
                    claim_ids=["claim_flannan_1900_hesperus_arrival"],
                ),
                NarrationSegmentInput(
                    scene_index=1,
                    text=(
                        "All three keepers—James Ducat, Thomas Marshall, and Donald McArthur—"
                        "had vanished into the Atlantic storm, leaving the station locked and silent."
                    ),
                    pause_after_sec=0.55,
                    claim_ids=["claim_flannan_1900_three_keepers_missing"],
                ),
            ]

            effective_settings = (
                settings.model_copy(update={"tts_engine": args.tts_engine})
                if args.tts_engine
                else settings
            )
            vo_gen = VoiceoverGenerator(settings=effective_settings, db=db)
            vo_result = vo_gen.generate_episode_voiceover(
                episode_id=args.episode_id,
                segments=segments_in,
                output_dir=out_root,
                min_total_duration_sec=15.0,
            )

            ass_path, cues = write_episode_subtitles(
                episode_id=args.episode_id,
                segments=vo_result.segments,
                output_dir=out_root,
                db=db,
            )

            transition_sec = 0.5
            seg0 = vo_result.segments[0]
            seg1 = vo_result.segments[1]
            scene0_dur = round(seg0.total_duration_sec + (transition_sec / 2.0), 3)
            scene1_dur = round(
                max(
                    1.0,
                    vo_result.total_duration_sec - seg0.total_duration_sec + (transition_sec / 2.0),
                ),
                3,
            )

            scenes = [
                SceneRenderSpec(
                    scene_index=0,
                    duration_sec=scene0_dur,
                    camera_motion=CameraMotionType.SLOW_PUSH_IN,
                    layers=[
                        SceneLayer(
                            layer_id="scene0_main",
                            role=LayerRole.COMPOSITE,
                            image_path=args.scene0_image,
                            z_index=0,
                        )
                    ],
                ),
                SceneRenderSpec(
                    scene_index=1,
                    duration_sec=scene1_dur,
                    camera_motion=CameraMotionType.PAN_UP_REVEAL,
                    layers=[
                        SceneLayer(
                            layer_id="scene1_main",
                            role=LayerRole.COMPOSITE,
                            image_path=args.scene1_image,
                            z_index=0,
                        )
                    ],
                ),
            ]

            assembler = VideoAssembler(settings=settings, db=db)
            render_result = assembler.render_episode(
                episode_id=args.episode_id,
                scenes=scenes,
                narration_wav=vo_result.audio_path,
                subtitle_ass=ass_path,
                output_filename=args.output_filename,
                transition_sec=transition_sec,
                upscale_factor=args.upscale_factor,
                output_dir=out_root,
            )

            summary = {
                "voiceover": json.loads(vo_result.model_dump_json()),
                "subtitle_ass_path": str(ass_path),
                "subtitle_cue_count": len(cues),
                "video": json.loads(render_result.model_dump_json()),
            }
            print(json.dumps(summary, indent=2))
            return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
