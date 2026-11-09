"""Automated unit and integration tests for Milestone M3 (Voiceover, Subtitles, and 1080x1920 Video Assembly)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from storytelling.config import Settings
from storytelling.db import DatabaseManager
from storytelling.models import AssetType, EpisodeRecord, StoryRecord
from storytelling.subtitles import (
    format_ass_timestamp,
    render_ass_document,
    split_segment_into_phrase_cues,
    write_episode_subtitles,
)
from storytelling.video_prod import (
    CameraMotionType,
    LayerRole,
    SceneLayer,
    SceneRenderSpec,
    VideoAssembler,
    build_episode_filter_complex,
    escape_ffmpeg_filter_path,
)
from storytelling.voiceover import (
    NarrationSegmentInput,
    PiperOfflineProvider,
    SAPI5OfflineProvider,
    SynthesizedSegment,
    TTSError,
    TTSProvider,
    VoiceoverGenerator,
    create_tts_provider,
    normalize_audio_peaks,
)


class FakeSineTTSProvider(TTSProvider):
    """Deterministic offline test provider generating a clean 220 Hz sine wave proportional to text length."""

    engine_name = "fake_sine_tts"
    voice_id = "test_voice_v1"
    license_id = "cc0-1.0"
    rights_provenance = "Synthetic unit-test sine wave generator"

    def synthesize_to_wav(self, text: str, output_wav: Path) -> None:
        cleaned = text.strip()
        if not cleaned:
            raise TTSError("Empty text")
        sr = 22050
        duration_sec = max(0.8, min(3.0, len(cleaned) * 0.025))
        t = np.linspace(0.0, duration_sec, int(sr * duration_sec), endpoint=False)
        samples = (0.4 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_wav), samples, sr, subtype="PCM_16")


def _seed_story_and_episode(db: DatabaseManager, episode_id: str = "ep_m3_test") -> None:
    db.apply_migrations()
    db.upsert_story(
        StoryRecord(
            story_id="story_m3",
            title="Flannan Isles Test Story",
            event_key="flannan-isles-1900-test",
        )
    )
    db.upsert_episode(
        EpisodeRecord(
            episode_id=episode_id,
            story_id="story_m3",
            series_index=1,
            title="Test Episode M3",
        )
    )


def test_tts_provider_fallback_when_piper_unavailable(tmp_path: Path) -> None:
    settings = Settings(
        db_path=tmp_path / "test.db",
        output_dir=tmp_path / "out",
        tts_engine="piper",
        piper_executable="nonexistent_piper_binary_xyz",
        piper_model_path=tmp_path / "missing_model.onnx",
    )
    provider = create_tts_provider(settings, allow_fallback_to_sapi5=True)
    assert isinstance(provider, SAPI5OfflineProvider)

    with pytest.raises(TTSError, match="Piper requested"):
        create_tts_provider(settings, allow_fallback_to_sapi5=False)


def test_piper_provider_availability_check(tmp_path: Path) -> None:
    provider = PiperOfflineProvider(
        piper_executable="nonexistent_piper_binary_xyz",
        model_path=tmp_path / "missing.onnx",
    )
    assert not provider.is_available()
    with pytest.raises(TTSError, match="not installed"):
        provider.synthesize_to_wav("Hello world", tmp_path / "out.wav")


def test_voiceover_generator_segmented_timing_and_db_records(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test.db")
    _seed_story_and_episode(db, "ep_vo_test")
    settings = Settings(db_path=db.db_path, output_dir=tmp_path / "output")

    vo_gen = VoiceoverGenerator(
        settings=settings,
        db=db,
        provider=FakeSineTTSProvider(),
    )
    segments = [
        NarrationSegmentInput(
            scene_index=0,
            text="In December nineteen hundred, the lighthouse fell silent.",
            pause_after_sec=0.4,
            claim_ids=["claim_1"],
        ),
        NarrationSegmentInput(
            scene_index=1,
            text="Three keepers vanished without a trace in the Atlantic storm.",
            pause_after_sec=0.5,
            claim_ids=["claim_2"],
        ),
    ]
    result = vo_gen.generate_episode_voiceover(
        episode_id="ep_vo_test",
        segments=segments,
        min_total_duration_sec=6.0,
    )

    assert result.audio_path.exists()
    assert result.manifest_path.exists()
    assert result.total_duration_sec >= 6.0
    assert not result.clipping_detected
    assert 0.80 <= result.peak_amplitude <= 0.86
    assert len(result.segments) == 2
    assert result.segments[0].start_sec == 0.0
    assert result.segments[0].speech_end_sec < result.segments[0].end_sec
    assert result.segments[1].start_sec == result.segments[0].end_sec

    assets = db.list_assets("ep_vo_test")
    assert any(a.asset_type == AssetType.AUDIO_NARRATION for a in assets)


def test_subtitle_cue_timing_and_ass_formatting(tmp_path: Path) -> None:
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(14.756) == "0:00:14.76"
    assert format_ass_timestamp(65.5) == "0:01:05.50"

    long_seg = SynthesizedSegment(
        segment_index=0,
        scene_index=0,
        text=(
            "In December nineteen hundred, the relief vessel Hesperus reached "
            "the isolated lighthouse on Eilean Mor, finding the landing empty."
        ),
        start_sec=0.0,
        speech_end_sec=6.4,
        end_sec=7.0,
        speech_duration_sec=6.4,
        total_duration_sec=7.0,
        claim_ids=["claim_1"],
    )
    cues = split_segment_into_phrase_cues(long_seg, max_chars_per_cue=68)
    assert len(cues) >= 2
    assert cues[0].start_sec == 0.0
    # Must never spill past speech_end_sec (6.4s) into the silent pause [6.4s, 7.0s]
    assert cues[-1].end_sec == 6.4
    for idx in range(1, len(cues)):
        assert cues[idx].start_sec == cues[idx - 1].end_sec

    db = DatabaseManager(tmp_path / "test.db")
    _seed_story_and_episode(db, "ep_sub_test")
    ass_path, written_cues = write_episode_subtitles(
        episode_id="ep_sub_test",
        segments=[long_seg],
        output_dir=tmp_path / "output",
        db=db,
    )
    assert ass_path.exists()
    content = ass_path.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert ",380,1" in content  # MarginV=380 safe zone
    assert len(written_cues) == len(cues)


def test_filter_complex_builder_and_windows_path_escaping(tmp_path: Path) -> None:
    sub_file = tmp_path / "captions.ass"
    sub_file.write_text("[Script Info]\n", encoding="utf-8")
    escaped = escape_ffmpeg_filter_path(sub_file)
    assert escaped.startswith("'") and escaped.endswith("'")
    assert "\\:" in escaped or "/" in escaped

    scenes = [
        SceneRenderSpec(
            scene_index=0,
            duration_sec=7.75,
            camera_motion=CameraMotionType.SLOW_PUSH_IN,
            layers=[
                SceneLayer(
                    layer_id="bg",
                    role=LayerRole.BACKGROUND,
                    image_path=tmp_path / "bg.png",
                    z_index=0,
                ),
                SceneLayer(
                    layer_id="char",
                    role=LayerRole.CHARACTER,
                    image_path=tmp_path / "char.png",
                    z_index=1,
                ),
            ],
        ),
        SceneRenderSpec(
            scene_index=1,
            duration_sec=7.75,
            camera_motion=CameraMotionType.PAN_UP_REVEAL,
            layers=[
                SceneLayer(
                    layer_id="s1",
                    role=LayerRole.COMPOSITE,
                    image_path=tmp_path / "s1.png",
                    z_index=0,
                )
            ],
        ),
    ]
    assert scenes[0].primary_image_path == tmp_path / "bg.png"

    fc_1x, total_dur_1x = build_episode_filter_complex(
        scenes,
        subtitle_path=sub_file,
        transition_sec=0.5,
        upscale_factor=1,
    )
    assert total_dur_1x == 15.0
    assert "scale=1080:1920" in fc_1x
    assert "xfade=transition=fade:duration=0.5:offset=7.25" in fc_1x
    assert "subtitles=filename=" in fc_1x

    fc_2x, total_dur_2x = build_episode_filter_complex(
        scenes,
        subtitle_path=sub_file,
        transition_sec=0.5,
        upscale_factor=2,
    )
    assert total_dur_2x == 15.0
    assert "scale=2160:3840" in fc_2x
    assert "s=1080x1920" in fc_2x


def test_end_to_end_video_assembler_1080x1920(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test.db")
    _seed_story_and_episode(db, "ep_render_test")
    settings = Settings(db_path=db.db_path, output_dir=tmp_path / "output")

    img0 = tmp_path / "scene0.png"
    img1 = tmp_path / "scene1.png"
    Image.new("RGB", (512, 896), color=(14, 28, 38)).save(img0)
    Image.new("RGB", (512, 896), color=(28, 22, 16)).save(img1)

    vo_gen = VoiceoverGenerator(
        settings=settings, db=db, provider=FakeSineTTSProvider()
    )
    vo_res = vo_gen.generate_episode_voiceover(
        episode_id="ep_render_test",
        segments=[
            NarrationSegmentInput(
                scene_index=0,
                text="Scene one test narration.",
                pause_after_sec=0.2,
            ),
            NarrationSegmentInput(
                scene_index=1,
                text="Scene two test narration.",
                pause_after_sec=0.2,
            ),
        ],
        min_total_duration_sec=2.5,
    )
    ass_path, _ = write_episode_subtitles(
        episode_id="ep_render_test",
        segments=vo_res.segments,
        output_dir=settings.output_dir,
        db=db,
    )

    scenes = [
        SceneRenderSpec(
            scene_index=0,
            duration_sec=1.5,
            camera_motion=CameraMotionType.SLOW_PUSH_IN,
            layers=[SceneLayer(layer_id="l0", image_path=img0)],
        ),
        SceneRenderSpec(
            scene_index=1,
            duration_sec=1.5,
            camera_motion=CameraMotionType.PAN_UP_REVEAL,
            layers=[SceneLayer(layer_id="l1", image_path=img1)],
        ),
    ]
    assembler = VideoAssembler(settings=settings, db=db)
    render_res = assembler.render_episode(
        episode_id="ep_render_test",
        scenes=scenes,
        narration_wav=vo_res.audio_path,
        subtitle_ass=ass_path,
        output_filename="test_1080x1920.mp4",
        transition_sec=0.5,
        upscale_factor=1,
    )

    assert render_res.video_path.exists()
    assert render_res.manifest_path.exists()
    assert render_res.probe.width == 1080
    assert render_res.probe.height == 1920
    assert render_res.probe.video_codec == "h264"
    assert render_res.probe.pix_fmt == "yuv420p"
    assert render_res.probe.audio_codec == "aac"
    assert 2.3 <= render_res.probe.duration_sec <= 2.7

    assets = db.list_assets("ep_render_test")
    asset_types = {a.asset_type for a in assets}
    assert AssetType.VIDEO_MP4 in asset_types
    assert AssetType.MANIFEST in asset_types
    assert AssetType.SUBTITLE in asset_types
    assert AssetType.AUDIO_NARRATION in asset_types
