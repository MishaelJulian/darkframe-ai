"""Typed configuration and budget/resource safety guards."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderChoice(StrEnum):
    """Supported LLM backend providers."""

    FILE = "file"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class StylePresetChoice(StrEnum):
    """Configurable dark 2D visual style presets."""

    DARK_CINEMATIC_2D = "DARK_CINEMATIC_2D"
    INKED_GRAPHIC_NOVEL = "INKED_GRAPHIC_NOVEL"
    ILLUSTRATED_NOIR = "ILLUSTRATED_NOIR"
    DARK_2D_ANIMATION = "DARK_2D_ANIMATION"



class ConfigurationError(ValueError):
    """Raised when configuration violates safety or budget guardrails."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Environment & Paths
    app_env: Literal["development", "test", "production"] = "development"
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")
    prompts_io_dir: Path = Path("prompts_io")
    db_path: Path = Path("data/storytelling.db")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Non-negotiable Cost, Budget & Safety Guards
    allow_paid_apis: bool = False
    allow_gemini_api: bool = False
    publishing_enabled: bool = False
    max_concurrent_gpu_jobs: int = Field(default=1, ge=1, le=1)
    monthly_budget_inr: float = Field(default=0.0, ge=0.0)
    per_job_budget_inr: float = Field(default=0.0, ge=0.0)

    # LLM Provider Configuration
    llm_provider: LLMProviderChoice = LLMProviderChoice.FILE
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"

    # Local ComfyUI Settings (RTX 4050 6 GB VRAM)
    comfyui_host: str = "127.0.0.1"
    comfyui_port: int = Field(default=8188, ge=1, le=65535)
    comfyui_fallback_port: int = Field(default=8000, ge=1, le=65535)
    comfyui_shared_models_dir: Path = Path(
        "C:/Users/misha/AppData/Local/Comfy-Desktop/ComfyUI-Shared/models"
    )
    comfyui_default_width: int = Field(default=512, ge=256, le=1024)
    comfyui_default_height: int = Field(default=896, ge=256, le=1024)
    comfyui_steps: int = Field(default=24, ge=1, le=50)
    comfyui_batch_size: int = Field(default=1, ge=1, le=1)
    default_style_preset: StylePresetChoice = StylePresetChoice.DARK_CINEMATIC_2D

    # Local Voiceover & FFmpeg Settings
    tts_engine: Literal["piper", "pyttsx3"] = "piper"
    piper_executable: str = "tools/piper/piper/piper.exe"
    piper_model_path: Path | None = Path("models/piper/en_US-norman-medium.onnx")
    ffmpeg_executable: str = "ffmpeg"
    ffprobe_executable: str = "ffprobe"

    @field_validator("max_concurrent_gpu_jobs")
    @classmethod
    def enforce_single_gpu_job_on_6gb_vram(cls, value: int) -> int:
        if value != 1:
            raise ConfigurationError(
                "MAX_CONCURRENT_GPU_JOBS must be 1 on RTX 4050 (6 GB VRAM)."
            )
        return value

    @model_validator(mode="after")
    def validate_provider_and_budget_guards(self) -> Settings:
        if not self.allow_paid_apis and (
            self.monthly_budget_inr > 0.0 or self.per_job_budget_inr > 0.0
        ):
            raise ConfigurationError(
                "Non-zero rupee budget requires ALLOW_PAID_APIS=true."
            )

        if self.llm_provider == LLMProviderChoice.GEMINI:
            if not self.allow_gemini_api:
                raise ConfigurationError(
                    "LLM_PROVIDER=gemini requires explicit opt-in via ALLOW_GEMINI_API=true."
                )
            if not self.gemini_api_key.get_secret_value().strip():
                raise ConfigurationError(
                    "LLM_PROVIDER=gemini requires a non-empty GEMINI_API_KEY."
                )
        return self


def load_settings(**overrides: object) -> Settings:
    """Load and validate application settings."""
    return Settings(**overrides)  # type: ignore[arg-type]
