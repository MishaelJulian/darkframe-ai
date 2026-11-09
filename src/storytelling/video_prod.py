"""Local FFmpeg vertical video assembly (1080x1920), camera motion, transitions, and ffprobe validation."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from storytelling.config import Settings
from storytelling.db import DatabaseManager
from storytelling.models import AssetRecord, AssetType, JobRecord, utc_now_iso


class VideoProductionError(RuntimeError):
    """Raised when FFmpeg rendering or ffprobe verification fails."""


class CameraMotionType(StrEnum):
    """Supported 2D camera motions for scene stills."""

    SLOW_PUSH_IN = "slow_push_in"
    SLOW_PULL_OUT = "slow_pull_out"
    PAN_UP_REVEAL = "pan_up_reveal"
    PAN_DOWN_REVEAL = "pan_down_reveal"
    STATIC_HOLD = "static_hold"


class LayerRole(StrEnum):
    """Layer role within a scene composition (designed for M3 stills and future M3.5 2D character layers)."""

    COMPOSITE = "COMPOSITE"
    BACKGROUND = "BACKGROUND"
    MIDGROUND = "MIDGROUND"
    CHARACTER = "CHARACTER"
    FOREGROUND_PROP = "FOREGROUND_PROP"


class SceneLayer(BaseModel):
    """A single visual layer in a scene (supports single-image M3 and multi-plane M3.5)."""

    model_config = ConfigDict(extra="forbid")

    layer_id: str
    role: LayerRole = LayerRole.COMPOSITE
    image_path: Path
    z_index: int = Field(default=0, ge=0)
    parallax_weight: float = Field(default=1.0, ge=0.0, le=3.0)


class SceneRenderSpec(BaseModel):
    """Specification for rendering one animated scene in the episode timeline."""

    model_config = ConfigDict(extra="forbid")

    scene_index: int = Field(ge=0)
    layers: list[SceneLayer] = Field(min_length=1)
    duration_sec: float = Field(gt=0.5)
    camera_motion: CameraMotionType = CameraMotionType.SLOW_PUSH_IN

    @property
    def primary_image_path(self) -> Path:
        sorted_layers = sorted(self.layers, key=lambda item: item.z_index)
        return sorted_layers[0].image_path


class VideoProbeReport(BaseModel):
    """Validated ffprobe metadata for a rendered MP4."""

    model_config = ConfigDict(extra="forbid")

    width: int
    height: int
    video_codec: str
    pix_fmt: str
    fps: float
    audio_codec: str | None
    duration_sec: float


class VideoRenderResult(BaseModel):
    """Output contract for a rendered and validated episode MP4."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    manifest_asset_id: str
    job_key: str
    video_path: Path
    manifest_path: Path
    sha256_checksum: str
    byte_size: int
    render_seconds: float
    upscale_factor: int
    probe: VideoProbeReport


def escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a Windows or POSIX file path for safe embedding inside FFmpeg `subtitles='...'`."""
    posix = path.resolve().as_posix()
    # Escape backslashes, colons (Windows drive letter), and single quotes for libavfilter
    escaped = posix.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"'{escaped}'"


def build_scene_zoompan_filter(
    *,
    input_label: str,
    output_label: str,
    duration_sec: float,
    camera_motion: CameraMotionType,
    fps: int = 30,
    target_width: int = 1080,
    target_height: int = 1920,
    upscale_factor: int = 1,
) -> str:
    """Build an FFmpeg filter chain scaling a vertical scene still to 1080x1920 with smooth camera motion.

    Args:
        upscale_factor: 1 for direct 1080x1920 rendering (lowest CPU/RAM), or 2 for 2160x3840 oversampled zoompan.
    """
    frames = max(1, int(round(duration_sec * fps)))
    work_w = target_width * upscale_factor
    work_h = target_height * upscale_factor

    if camera_motion == CameraMotionType.SLOW_PUSH_IN:
        z_expr = f"1.0+0.10*(on/{frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera_motion == CameraMotionType.SLOW_PULL_OUT:
        z_expr = f"1.10-0.10*(on/{frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera_motion == CameraMotionType.PAN_UP_REVEAL:
        z_expr = "1.10"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(1.0-on/{frames})"
    elif camera_motion == CameraMotionType.PAN_DOWN_REVEAL:
        z_expr = "1.10"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(on/{frames})"
    else:
        z_expr = "1.0"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    return (
        f"[{input_label}]scale={work_w}:{work_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={work_w}:{work_h},setsar=1,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={target_width}x{target_height}:fps={fps},"
        f"format=yuv420p[{output_label}]"
    )


def build_episode_filter_complex(
    scenes: list[SceneRenderSpec],
    *,
    subtitle_path: Path | None = None,
    transition_sec: float = 0.5,
    fade_in_sec: float = 0.5,
    fade_out_sec: float = 0.6,
    fps: int = 30,
    target_width: int = 1080,
    target_height: int = 1920,
    upscale_factor: int = 1,
) -> tuple[str, float]:
    """Construct complete FFmpeg `-filter_complex` for multi-scene camera animation, xfade, fades, and subtitles."""
    if not scenes:
        raise VideoProductionError("At least one SceneRenderSpec is required.")

    filter_parts: list[str] = []
    for idx, scene in enumerate(scenes):
        filter_parts.append(
            build_scene_zoompan_filter(
                input_label=f"{idx}:v",
                output_label=f"v{idx}",
                duration_sec=scene.duration_sec,
                camera_motion=scene.camera_motion,
                fps=fps,
                target_width=target_width,
                target_height=target_height,
                upscale_factor=upscale_factor,
            )
        )

    if len(scenes) == 1:
        total_duration = scenes[0].duration_sec
        current_label = "v0"
    else:
        current_label = "v0"
        accumulated = scenes[0].duration_sec
        for idx in range(1, len(scenes)):
            next_label = f"v{idx}"
            out_label = f"xf{idx}"
            offset = max(0.0, round(accumulated - transition_sec, 3))
            filter_parts.append(
                f"[{current_label}][{next_label}]xfade=transition=fade:duration={transition_sec}:offset={offset}[{out_label}]"
            )
            accumulated = offset + scenes[idx].duration_sec
            current_label = out_label
        total_duration = round(accumulated, 3)

    fade_out_start = max(0.0, round(total_duration - fade_out_sec, 3))
    post_chain = (
        f"[{current_label}]fade=t=in:st=0:d={fade_in_sec},"
        f"fade=t=out:st={fade_out_start}:d={fade_out_sec}"
    )
    if subtitle_path is not None:
        escaped_sub = escape_ffmpeg_filter_path(subtitle_path)
        post_chain += f",subtitles=filename={escaped_sub}"
    post_chain += ",format=yuv420p[vout]"
    filter_parts.append(post_chain)

    return ";".join(filter_parts), total_duration


def probe_video_file(video_path: Path, ffprobe_executable: str = "ffprobe") -> VideoProbeReport:
    """Validate rendered MP4 stream metadata via `ffprobe`."""
    if not shutil.which(ffprobe_executable) and not Path(ffprobe_executable).exists():
        raise VideoProductionError(f"ffprobe executable not found: {ffprobe_executable}")
    if not video_path.exists():
        raise VideoProductionError(f"Rendered video file not found: {video_path}")

    cmd = [
        ffprobe_executable,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate:format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode != 0:
        raise VideoProductionError(f"ffprobe failed: {proc.stderr}")

    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise VideoProductionError(f"Invalid JSON from ffprobe: {exc}") from exc

    streams = payload.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video_stream is None:
        raise VideoProductionError(f"No video stream found in {video_path}")

    fps_str = str(video_stream.get("r_frame_rate", "30/1"))
    if "/" in fps_str:
        num, den = fps_str.split("/", 1)
        fps_val = float(num) / max(1.0, float(den))
    else:
        fps_val = float(fps_str)

    duration_sec = float(payload.get("format", {}).get("duration", 0.0))
    return VideoProbeReport(
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        video_codec=str(video_stream.get("codec_name", "")),
        pix_fmt=str(video_stream.get("pix_fmt", "")),
        fps=round(fps_val, 2),
        audio_codec=str(audio_stream["codec_name"]) if audio_stream else None,
        duration_sec=round(duration_sec, 3),
    )


class VideoAssembler:
    """Renders 1080x1920 vertical H.264 MP4 episodes from scenes, narration WAV, and .ass captions."""

    def __init__(self, settings: Settings, db: DatabaseManager) -> None:
        self.settings = settings
        self.db = db

    def render_episode(
        self,
        *,
        episode_id: str,
        scenes: list[SceneRenderSpec],
        narration_wav: Path,
        subtitle_ass: Path | None = None,
        output_filename: str = "episode_1080x1920.mp4",
        transition_sec: float = 0.5,
        upscale_factor: int = 1,
        output_dir: Path | None = None,
    ) -> VideoRenderResult:
        """Assemble scenes, narration, and captions into a verified 1080x1920 H.264 MP4."""
        ffmpeg_exe = self.settings.ffmpeg_executable
        if not shutil.which(ffmpeg_exe) and not Path(ffmpeg_exe).exists():
            raise VideoProductionError(f"ffmpeg executable not found: {ffmpeg_exe}")
        if not narration_wav.exists():
            raise VideoProductionError(f"Narration WAV file not found: {narration_wav}")
        for sc in scenes:
            if not sc.primary_image_path.exists():
                raise VideoProductionError(
                    f"Scene {sc.scene_index} image not found: {sc.primary_image_path}"
                )

        job_key = f"{episode_id}:video_render:upscale_{upscale_factor}x:{output_filename}"
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self.db.register_job(
            JobRecord(
                job_id=job_id,
                job_key=job_key,
                episode_id=episode_id,
                stage="VIDEO_PRODUCTION",
                uses_gpu=False,
            )
        )
        self.db.start_job(job_key)
        start_time = time.monotonic()

        try:
            target_dir = (output_dir or self.settings.output_dir) / episode_id / "video"
            target_dir.mkdir(parents=True, exist_ok=True)
            video_path = target_dir / output_filename
            manifest_path = target_dir / f"{ video_path.stem }.manifest.json"

            filter_complex, expected_duration = build_episode_filter_complex(
                scenes,
                subtitle_path=subtitle_ass,
                transition_sec=transition_sec,
                upscale_factor=upscale_factor,
            )

            cmd: list[str] = [ffmpeg_exe, "-y"]
            for sc in scenes:
                cmd.extend(["-i", str(sc.primary_image_path)])
            audio_input_idx = len(scenes)
            cmd.extend(["-i", str(narration_wav)])

            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[vout]",
                    "-map",
                    f"{audio_input_idx}:a",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "30",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-t",
                    f"{expected_duration:.3f}",
                    "-movflags",
                    "+faststart",
                    str(video_path),
                ]
            )

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300, check=False
            )
            if proc.returncode != 0:
                raise VideoProductionError(
                    f"FFmpeg render failed (exit {proc.returncode}): {proc.stderr[-1200:]}"
                )

            probe = probe_video_file(video_path, self.settings.ffprobe_executable)
            if (probe.width, probe.height) != (1080, 1920):
                raise VideoProductionError(
                    f"Invalid output resolution {probe.width}x{probe.height}; expected 1080x1920."
                )
            if probe.video_codec != "h264" or probe.audio_codec is None:
                raise VideoProductionError(
                    f"Invalid codecs in output: video={probe.video_codec}, audio={probe.audio_codec}"
                )

            render_seconds = round(max(0.0, time.monotonic() - start_time), 3)
            mp4_bytes = video_path.read_bytes()
            sha256_hex = hashlib.sha256(mp4_bytes).hexdigest()
            byte_size = len(mp4_bytes)

            manifest_payload: dict[str, Any] = {
                "episode_id": episode_id,
                "video_path": str(video_path),
                "narration_wav": str(narration_wav),
                "subtitle_ass": str(subtitle_ass) if subtitle_ass else None,
                "upscale_factor": upscale_factor,
                "transition_sec": transition_sec,
                "expected_duration_sec": expected_duration,
                "render_seconds": render_seconds,
                "sha256_checksum": sha256_hex,
                "byte_size": byte_size,
                "ffprobe": probe.model_dump(),
                "scenes": [
                    {
                        "scene_index": s.scene_index,
                        "duration_sec": s.duration_sec,
                        "camera_motion": s.camera_motion.value,
                        "layers": [
                            {
                                "layer_id": lyr.layer_id,
                                "role": lyr.role.value,
                                "image_path": str(lyr.image_path),
                                "z_index": lyr.z_index,
                                "parallax_weight": lyr.parallax_weight,
                            }
                            for lyr in s.layers
                        ],
                    }
                    for s in scenes
                ],
                "created_at": utc_now_iso(),
            }
            manifest_path.write_text(
                json.dumps(manifest_payload, indent=2), encoding="utf-8"
            )

            video_asset_id = f"ast_{uuid.uuid4().hex[:12]}"
            self.db.record_asset(
                AssetRecord(
                    asset_id=video_asset_id,
                    episode_id=episode_id,
                    asset_type=AssetType.VIDEO_MP4,
                    file_path=str(video_path),
                    sha256_checksum=sha256_hex,
                    byte_size=byte_size,
                    model_name="ffmpeg_libx264",
                    model_version="8.0.1",
                    license_id="commercial-owned",
                    rights_provenance="Locally assembled vertical video from verified project assets",
                    metadata_json=manifest_payload,
                )
            )

            manifest_bytes = manifest_path.read_bytes()
            manifest_asset_id = f"ast_{uuid.uuid4().hex[:12]}"
            self.db.record_asset(
                AssetRecord(
                    asset_id=manifest_asset_id,
                    episode_id=episode_id,
                    asset_type=AssetType.MANIFEST,
                    file_path=str(manifest_path),
                    sha256_checksum=hashlib.sha256(manifest_bytes).hexdigest(),
                    byte_size=len(manifest_bytes),
                    model_name="darkframe_render_manifest",
                    model_version="v1",
                    license_id="commercial-owned",
                    rights_provenance="Internal render manifest",
                    metadata_json={"video_asset_id": video_asset_id},
                )
            )
            self.db.complete_job(job_key, gpu_seconds=0.0)

            return VideoRenderResult(
                asset_id=video_asset_id,
                manifest_asset_id=manifest_asset_id,
                job_key=job_key,
                video_path=video_path,
                manifest_path=manifest_path,
                sha256_checksum=sha256_hex,
                byte_size=byte_size,
                render_seconds=render_seconds,
                upscale_factor=upscale_factor,
                probe=probe,
            )
        except Exception as exc:
            self.db.fail_job(job_key, error_message=str(exc), gpu_seconds=0.0)
            raise
