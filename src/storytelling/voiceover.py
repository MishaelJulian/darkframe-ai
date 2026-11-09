"""Offline Text-to-Speech (TTS) narration engine supporting Piper and Windows SAPI5 (pyttsx3)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from pydantic import BaseModel, ConfigDict, Field

from storytelling.config import Settings
from storytelling.db import DatabaseManager
from storytelling.models import AssetRecord, AssetType, JobRecord, utc_now_iso


class TTSError(RuntimeError):
    """Raised when local TTS synthesis or audio normalization fails."""


class NarrationSegmentInput(BaseModel):
    """Input contract for a single narrated scene or sentence segment."""

    model_config = ConfigDict(extra="forbid")

    scene_index: int = Field(ge=0)
    text: str
    pause_after_sec: float = Field(default=0.35, ge=0.0, le=5.0)
    claim_ids: list[str] = Field(default_factory=list)


class SynthesizedSegment(BaseModel):
    """Exact timing and provenance for a synthesized narration segment."""

    model_config = ConfigDict(extra="forbid")

    segment_index: int = Field(ge=0)
    scene_index: int = Field(ge=0)
    text: str
    start_sec: float = Field(ge=0.0)
    speech_end_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    speech_duration_sec: float = Field(gt=0.0)
    total_duration_sec: float = Field(gt=0.0)
    claim_ids: list[str] = Field(default_factory=list)


class VoiceoverResult(BaseModel):
    """Output contract for episode voiceover synthesis."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    job_key: str
    audio_path: Path
    manifest_path: Path
    sha256_checksum: str
    byte_size: int
    engine_name: str
    voice_id: str
    license_id: str
    rights_provenance: str
    sample_rate: int
    total_duration_sec: float
    peak_amplitude: float
    clipping_detected: bool
    segments: list[SynthesizedSegment]


class TTSProvider(ABC):
    """Abstract interface for offline TTS providers."""

    engine_name: str
    voice_id: str
    license_id: str
    rights_provenance: str

    @abstractmethod
    def synthesize_to_wav(self, text: str, output_wav: Path) -> None:
        """Synthesize `text` to a mono WAV file at `output_wav`."""


class SAPI5OfflineProvider(TTSProvider):
    """Offline Windows SAPI5 TTS provider via `pyttsx3` (zero download required)."""

    engine_name = "pyttsx3_sapi5"

    def __init__(self, rate_wpm: int = 152, preferred_voice_substring: str = "David") -> None:
        self.rate_wpm = rate_wpm
        self.preferred_voice_substring = preferred_voice_substring
        self.voice_id = "Microsoft David Desktop (SAPI5)"
        self.license_id = "windows-os-sapi5"
        self.rights_provenance = "Offline Windows SAPI5 built-in system voice"

    def synthesize_to_wav(self, text: str, output_wav: Path) -> None:
        cleaned = text.strip()
        if not cleaned:
            raise TTSError("Cannot synthesize empty narration text.")
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        try:
            import pyttsx3

            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
            for v in voices:
                if self.preferred_voice_substring.lower() in str(getattr(v, "name", "")).lower():
                    engine.setProperty("voice", v.id)
                    self.voice_id = str(getattr(v, "name", v.id))
                    break
            engine.setProperty("rate", self.rate_wpm)
            engine.save_to_file(cleaned, str(output_wav))
            engine.runAndWait()
        except Exception as exc:
            raise TTSError(f"pyttsx3 SAPI5 synthesis failed: {exc}") from exc

        if not output_wav.exists() or output_wav.stat().st_size == 0:
            raise TTSError(f"pyttsx3 did not produce a valid WAV file at {output_wav}")


class PiperOfflineProvider(TTSProvider):
    """Offline neural TTS provider using local Piper executable and ONNX model."""

    engine_name = "piper_onnx"

    def __init__(
        self,
        piper_executable: str | Path,
        model_path: Path,
        license_id: str = "cc0-1.0",
        rights_provenance: str = "Offline Piper ONNX voice model",
        length_scale: float = 1.08,
    ) -> None:
        self.piper_executable = str(piper_executable)
        self.model_path = Path(model_path)
        self.voice_id = self.model_path.stem
        self.license_id = license_id
        self.rights_provenance = rights_provenance
        self.length_scale = length_scale

    def is_available(self) -> bool:
        exe_ok = bool(
            shutil.which(self.piper_executable) or Path(self.piper_executable).exists()
        )
        return exe_ok and self.model_path.exists()

    def synthesize_to_wav(self, text: str, output_wav: Path) -> None:
        cleaned = text.strip()
        if not cleaned:
            raise TTSError("Cannot synthesize empty narration text.")
        if not self.is_available():
            raise TTSError(
                f"Piper executable ({self.piper_executable}) or voice model ({self.model_path}) is not installed."
            )
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.piper_executable,
            "--model",
            str(self.model_path),
            "--output_file",
            str(output_wav),
            "--length_scale",
            str(self.length_scale),
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=cleaned.encode("utf-8"),
                capture_output=True,
                timeout=60,
                check=False,
            )
        except Exception as exc:
            raise TTSError(f"Failed executing Piper TTS: {exc}") from exc

        if proc.returncode != 0 or not output_wav.exists() or output_wav.stat().st_size == 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")
            raise TTSError(f"Piper TTS failed (exit {proc.returncode}): {stderr}")


def create_tts_provider(
    settings: Settings, *, allow_fallback_to_sapi5: bool = True
) -> TTSProvider:
    """Resolve configured offline TTS provider with optional fallback to SAPI5 (`pyttsx3`)."""
    if settings.tts_engine == "piper" and settings.piper_model_path is not None:
        piper = PiperOfflineProvider(
            piper_executable=settings.piper_executable,
            model_path=settings.piper_model_path,
        )
        if piper.is_available():
            return piper
        if not allow_fallback_to_sapi5:
            raise TTSError(
                f"Piper requested but model/binary not found at {settings.piper_model_path}"
            )
    return SAPI5OfflineProvider()


def read_mono_wav_samples(wav_path: Path, target_sr: int = 22050) -> tuple[np.ndarray, int]:
    """Read a WAV file into float32 mono samples at `target_sr`."""
    data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != target_sr:
        # Linear resample using numpy interpolation for deterministic zero-dependency resampling
        duration = len(mono) / float(sr)
        new_len = max(1, int(round(duration * target_sr)))
        old_idx = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
        new_idx = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
        mono = np.interp(new_idx, old_idx, mono).astype(np.float32)
    return mono, target_sr


def normalize_audio_peaks(
    samples: np.ndarray, target_peak_db: float = -1.5
) -> tuple[np.ndarray, float, bool]:
    """Normalize audio to `target_peak_db` below full scale and report peak/clipping."""
    raw_peak = float(np.max(np.abs(samples))) if len(samples) > 0 else 0.0
    clipping_detected = raw_peak > 0.999
    if raw_peak > 1e-6:
        target_linear = float(10.0 ** (target_peak_db / 20.0))
        scaled = (samples / raw_peak) * target_linear
    else:
        scaled = samples
    final_peak = float(np.max(np.abs(scaled))) if len(scaled) > 0 else 0.0
    return np.clip(scaled, -1.0, 1.0).astype(np.float32), final_peak, clipping_detected


class VoiceoverGenerator:
    """Synthesizes segmented narration, records exact timings, and persists SQLite assets."""

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        provider: TTSProvider | None = None,
        sample_rate: int = 22050,
    ) -> None:
        self.settings = settings
        self.db = db
        self.provider = provider or create_tts_provider(settings)
        self.sample_rate = sample_rate

    def generate_episode_voiceover(
        self,
        episode_id: str,
        segments: list[NarrationSegmentInput],
        output_dir: Path | None = None,
        min_total_duration_sec: float | None = None,
    ) -> VoiceoverResult:
        """Synthesize each segment individually to capture exact timestamps, then assemble `narration.wav`."""
        if not segments:
            raise TTSError("At least one NarrationSegmentInput is required.")

        job_key = f"{episode_id}:voiceover:{self.provider.engine_name}"
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self.db.register_job(
            JobRecord(
                job_id=job_id,
                job_key=job_key,
                episode_id=episode_id,
                stage="VOICEOVER",
                uses_gpu=False,
            )
        )
        self.db.start_job(job_key)

        try:
            target_dir = (output_dir or self.settings.output_dir) / episode_id / "audio"
            seg_dir = target_dir / "segments"
            seg_dir.mkdir(parents=True, exist_ok=True)

            assembled_chunks: list[np.ndarray] = []
            synthesized_segments: list[SynthesizedSegment] = []
            cursor_sec = 0.0

            for idx, seg in enumerate(segments):
                seg_wav = seg_dir / f"seg_{idx:02d}_scene_{seg.scene_index:02d}.wav"
                self.provider.synthesize_to_wav(seg.text, seg_wav)
                speech_samples, _ = read_mono_wav_samples(seg_wav, target_sr=self.sample_rate)
                # Trim leading/trailing digital silence (> -50 dB threshold) while keeping natural breath
                non_silent = np.where(np.abs(speech_samples) > 0.003)[0]
                if len(non_silent) > 0:
                    pad = int(0.04 * self.sample_rate)
                    start_i = max(0, int(non_silent[0]) - pad)
                    end_i = min(len(speech_samples), int(non_silent[-1]) + pad)
                    speech_samples = speech_samples[start_i:end_i]

                speech_dur = len(speech_samples) / float(self.sample_rate)
                pause_samples = np.zeros(
                    int(round(seg.pause_after_sec * self.sample_rate)), dtype=np.float32
                )
                total_seg_samples = np.concatenate([speech_samples, pause_samples])
                total_seg_dur = len(total_seg_samples) / float(self.sample_rate)

                start_sec = round(cursor_sec, 3)
                speech_end_sec = round(cursor_sec + speech_dur, 3)
                end_sec = round(cursor_sec + total_seg_dur, 3)

                synthesized_segments.append(
                    SynthesizedSegment(
                        segment_index=idx,
                        scene_index=seg.scene_index,
                        text=seg.text.strip(),
                        start_sec=start_sec,
                        speech_end_sec=speech_end_sec,
                        end_sec=end_sec,
                        speech_duration_sec=round(speech_dur, 3),
                        total_duration_sec=round(total_seg_dur, 3),
                        claim_ids=seg.claim_ids,
                    )
                )
                assembled_chunks.append(total_seg_samples)
                cursor_sec += total_seg_dur

            if min_total_duration_sec is not None and cursor_sec < min_total_duration_sec:
                pad_sec = min_total_duration_sec - cursor_sec
                pad_samples = np.zeros(
                    int(round(pad_sec * self.sample_rate)), dtype=np.float32
                )
                assembled_chunks.append(pad_samples)
                cursor_sec = min_total_duration_sec
                # Extend the final segment's tail hold to match padded audio duration
                last = synthesized_segments[-1]
                synthesized_segments[-1] = last.model_copy(
                    update={
                        "end_sec": round(cursor_sec, 3),
                        "total_duration_sec": round(cursor_sec - last.start_sec, 3),
                    }
                )

            full_audio = np.concatenate(assembled_chunks)
            norm_audio, peak_amp, clipped = normalize_audio_peaks(
                full_audio, target_peak_db=-1.5
            )

            narration_wav = target_dir / "narration.wav"
            manifest_path = target_dir / "narration.manifest.json"
            sf.write(str(narration_wav), norm_audio, self.sample_rate, subtype="PCM_16")

            wav_bytes = narration_wav.read_bytes()
            sha256_hex = hashlib.sha256(wav_bytes).hexdigest()
            byte_size = len(wav_bytes)
            total_duration_sec = round(len(norm_audio) / float(self.sample_rate), 3)

            manifest_payload: dict[str, Any] = {
                "episode_id": episode_id,
                "engine_name": self.provider.engine_name,
                "voice_id": self.provider.voice_id,
                "license_id": self.provider.license_id,
                "rights_provenance": self.provider.rights_provenance,
                "sample_rate": self.sample_rate,
                "total_duration_sec": total_duration_sec,
                "peak_amplitude": round(peak_amp, 4),
                "clipping_detected": clipped,
                "sha256_checksum": sha256_hex,
                "byte_size": byte_size,
                "segments": [s.model_dump() for s in synthesized_segments],
                "created_at": utc_now_iso(),
            }
            manifest_path.write_text(
                json.dumps(manifest_payload, indent=2), encoding="utf-8"
            )

            asset_id = f"ast_{uuid.uuid4().hex[:12]}"
            self.db.record_asset(
                AssetRecord(
                    asset_id=asset_id,
                    episode_id=episode_id,
                    asset_type=AssetType.AUDIO_NARRATION,
                    file_path=str(narration_wav),
                    sha256_checksum=sha256_hex,
                    byte_size=byte_size,
                    model_name=self.provider.voice_id,
                    model_version=self.provider.engine_name,
                    license_id=self.provider.license_id,
                    rights_provenance=self.provider.rights_provenance,
                    metadata_json=manifest_payload,
                )
            )
            self.db.complete_job(job_key, gpu_seconds=0.0)

            return VoiceoverResult(
                asset_id=asset_id,
                job_key=job_key,
                audio_path=narration_wav,
                manifest_path=manifest_path,
                sha256_checksum=sha256_hex,
                byte_size=byte_size,
                engine_name=self.provider.engine_name,
                voice_id=self.provider.voice_id,
                license_id=self.provider.license_id,
                rights_provenance=self.provider.rights_provenance,
                sample_rate=self.sample_rate,
                total_duration_sec=total_duration_sec,
                peak_amplitude=round(peak_amp, 4),
                clipping_detected=clipped,
                segments=synthesized_segments,
            )
        except Exception as exc:
            self.db.fail_job(job_key, error_message=str(exc), gpu_seconds=0.0)
            raise
