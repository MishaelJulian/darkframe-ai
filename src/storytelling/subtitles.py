"""Synchronized sentence/phrase SubStation Alpha (.ass) subtitle generator for 1080x1920 vertical video."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from storytelling.db import DatabaseManager
from storytelling.models import AssetRecord, AssetType
from storytelling.voiceover import SynthesizedSegment


class SubtitleCue(BaseModel):
    """A single timed phrase/sentence caption cue."""

    model_config = ConfigDict(extra="forbid")

    cue_index: int = Field(ge=0)
    scene_index: int = Field(ge=0)
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(gt=0.0)
    text: str


def format_ass_timestamp(seconds: float) -> str:
    """Format seconds as `H:MM:SS.cc` (centiseconds) required by SubStation Alpha."""
    clamped = max(0.0, seconds)
    total_cs = int(round(clamped * 100))
    hours = total_cs // 360000
    rem = total_cs % 360000
    minutes = rem // 6000
    rem = rem % 6000
    secs = rem // 100
    cs = rem % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def split_segment_into_phrase_cues(
    segment: SynthesizedSegment,
    start_cue_index: int = 0,
    max_chars_per_cue: int = 64,
) -> list[SubtitleCue]:
    """Split a synthesized segment into phrase/sentence cues locked strictly inside [start_sec, speech_end_sec].

    To avoid fake word-level drift when only segment-level audio duration is known,
    each synthesized segment stays as a single synchronized sentence cue unless it exceeds
    `max_chars_per_cue` at a natural clause boundary (`. `, `; `, `, `, ` — `).
    """
    text = segment.text.strip()
    speech_start = segment.start_sec
    speech_end = max(segment.speech_end_sec, speech_start + 0.2)
    speech_span = speech_end - speech_start

    if len(text) <= max_chars_per_cue:
        return [
            SubtitleCue(
                cue_index=start_cue_index,
                scene_index=segment.scene_index,
                start_sec=round(speech_start, 3),
                end_sec=round(speech_end, 3),
                text=text,
            )
        ]

    # Split only on major punctuation pauses while keeping phrases substantial
    raw_clauses = [
        c.strip()
        for c in re.split(r"(?<=[.!?;:])\s+|(?<=,)\s+(?=[A-Za-z]{3,})", text)
        if c.strip()
    ]
    merged_phrases: list[str] = []
    current = ""
    for clause in raw_clauses:
        if not current:
            current = clause
        elif len(current) + 1 + len(clause) <= max_chars_per_cue:
            current = f"{current} {clause}"
        else:
            merged_phrases.append(current)
            current = clause
    if current:
        merged_phrases.append(current)

    if len(merged_phrases) <= 1:
        return [
            SubtitleCue(
                cue_index=start_cue_index,
                scene_index=segment.scene_index,
                start_sec=round(speech_start, 3),
                end_sec=round(speech_end, 3),
                text=text,
            )
        ]

    total_weight = sum(max(1, len(p)) for p in merged_phrases)
    cues: list[SubtitleCue] = []
    cursor = speech_start
    for idx, phrase in enumerate(merged_phrases):
        weight = max(1, len(phrase))
        dur = speech_span * (weight / float(total_weight))
        cue_end = speech_end if idx == len(merged_phrases) - 1 else cursor + dur
        cues.append(
            SubtitleCue(
                cue_index=start_cue_index + idx,
                scene_index=segment.scene_index,
                start_sec=round(cursor, 3),
                end_sec=round(cue_end, 3),
                text=phrase,
            )
        )
        cursor = cue_end
    return cues


def build_cues_from_segments(segments: list[SynthesizedSegment]) -> list[SubtitleCue]:
    """Build synchronized phrase/sentence cues from synthesized narration segments."""
    all_cues: list[SubtitleCue] = []
    for seg in segments:
        seg_cues = split_segment_into_phrase_cues(seg, start_cue_index=len(all_cues))
        all_cues.extend(seg_cues)
    return all_cues


def render_ass_document(
    cues: list[SubtitleCue],
    *,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    margin_v: int = 380,
    margin_h: int = 110,
    font_name: str = "Arial",
    font_size: int = 52,
) -> str:
    """Render a SubStation Alpha (.ass) subtitle document with Reels/Shorts safe margins."""
    header = (
        "[Script Info]\n"
        "Title: DarkFrame AI Captions\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},&H00E6F4FF,&H0000B4FF,&H00101418,&H80080A0C,"
        f"-1,0,0,0,100,100,0,0,1,4,2,2,{margin_h},{margin_h},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    for cue in cues:
        start_str = format_ass_timestamp(cue.start_sec)
        end_str = format_ass_timestamp(cue.end_sec)
        safe_text = cue.text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{safe_text}\n"
        )
    return "".join(lines)


def write_episode_subtitles(
    episode_id: str,
    segments: list[SynthesizedSegment],
    output_dir: Path,
    db: DatabaseManager | None = None,
) -> tuple[Path, list[SubtitleCue]]:
    """Generate and persist `captions.ass` for an episode, optionally registering in SQLite."""
    cues = build_cues_from_segments(segments)
    ass_text = render_ass_document(cues)

    sub_dir = output_dir / episode_id / "subtitles"
    sub_dir.mkdir(parents=True, exist_ok=True)
    ass_path = sub_dir / "captions.ass"
    ass_path.write_text(ass_text, encoding="utf-8")

    if db is not None:
        raw_bytes = ass_path.read_bytes()
        sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
        db.record_asset(
            AssetRecord(
                asset_id=f"ast_{uuid.uuid4().hex[:12]}",
                episode_id=episode_id,
                asset_type=AssetType.SUBTITLE,
                file_path=str(ass_path),
                sha256_checksum=sha256_hex,
                byte_size=len(raw_bytes),
                model_name="deterministic_phrase_sync",
                model_version="v1",
                license_id="cc0-1.0",
                rights_provenance="Generated internally from verified segment timings",
                metadata_json={"cue_count": len(cues), "cues": [c.model_dump() for c in cues]},
            )
        )
    return ass_path, cues
