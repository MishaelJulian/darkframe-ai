"""Modular LLM provider interface supporting file export/import, Gemini, and Ollama."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from storytelling.config import ConfigurationError, LLMProviderChoice, Settings
from storytelling.models import utc_now_iso


class LLMRequest(BaseModel):
    """Structured prompt request passed to any LLMProvider."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    task_type: str
    system_prompt: str
    user_prompt: str
    expected_schema_name: str
    expected_json_schema: dict[str, Any]
    created_at: str = Field(default_factory=utc_now_iso)


class LLMResponse(BaseModel):
    """Structured response returned by an LLMProvider."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    provider: LLMProviderChoice
    model_name: str
    structured_output: dict[str, Any]
    created_at: str = Field(default_factory=utc_now_iso)


class PendingManualResponseError(RuntimeError):
    """Raised when FileExportImportProvider has exported a prompt and awaits user import."""


class LLMProvider(ABC):
    """Abstract interface for interchangeable LLM backends."""

    provider_type: LLMProviderChoice

    @abstractmethod
    def generate_structured(self, request: LLMRequest) -> LLMResponse:
        """Generate or load a structured JSON response matching `request`."""


class FileExportImportProvider(LLMProvider):
    """Development provider that exports prompt bundles to disk and imports responses."""

    provider_type = LLMProviderChoice.FILE

    def __init__(self, prompts_io_dir: Path) -> None:
        self.prompts_io_dir = prompts_io_dir

    def request_path(self, request_id: str) -> Path:
        return self.prompts_io_dir / f"{request_id}.request.json"

    def prompt_markdown_path(self, request_id: str) -> Path:
        return self.prompts_io_dir / f"{request_id}.prompt.md"

    def response_path(self, request_id: str) -> Path:
        return self.prompts_io_dir / f"{request_id}.response.json"

    def export_prompt(self, request: LLMRequest) -> Path:
        """Write request JSON and human-friendly Markdown prompt for manual LLM runs."""
        self.prompts_io_dir.mkdir(parents=True, exist_ok=True)
        req_file = self.request_path(request.request_id)
        md_file = self.prompt_markdown_path(request.request_id)

        req_file.write_text(
            request.model_dump_json(indent=2),
            encoding="utf-8",
        )
        schema_str = json.dumps(request.expected_json_schema, indent=2)
        md_content = (
            f"# Prompt Bundle: `{request.request_id}` ({request.task_type})\n\n"
            f"## System Instructions\n\n{request.system_prompt}\n\n"
            f"## User Task\n\n{request.user_prompt}\n\n"
            f"## Expected JSON Schema (`{request.expected_schema_name}`)\n\n"
            f"```json\n{schema_str}\n```\n\n"
            f"Save the pure JSON output to: `{self.response_path(request.request_id)}`\n"
        )
        md_file.write_text(md_content, encoding="utf-8")
        return req_file

    def generate_structured(self, request: LLMRequest) -> LLMResponse:
        """Export prompt and load `<request_id>.response.json` if present."""
        self.export_prompt(request)
        resp_file = self.response_path(request.request_id)
        if not resp_file.exists():
            raise PendingManualResponseError(
                f"Prompt exported to {self.prompt_markdown_path(request.request_id)}. "
                f"Paste JSON response into {resp_file} and rerun."
            )
        raw_data = json.loads(resp_file.read_text(encoding="utf-8"))
        return LLMResponse(
            request_id=request.request_id,
            provider=LLMProviderChoice.FILE,
            model_name="manual-file-import",
            structured_output=raw_data,
        )


class GeminiAPIProvider(LLMProvider):
    """Future automated Gemini provider (guarded by ALLOW_GEMINI_API)."""

    provider_type = LLMProviderChoice.GEMINI

    def __init__(self, settings: Settings) -> None:
        if not settings.allow_gemini_api:
            raise ConfigurationError(
                "GeminiAPIProvider cannot be initialized when ALLOW_GEMINI_API=false."
            )
        self.settings = settings

    def generate_structured(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "Live Gemini API execution is scheduled for Milestone M5 after explicit quota/API approval."
        )


class OllamaLocalProvider(LLMProvider):
    """Optional local fallback provider via Ollama HTTP API."""

    provider_type = LLMProviderChoice.OLLAMA

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_structured(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "Ollama local execution is scheduled for Milestone M5."
        )


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Factory that instantiates the configured LLMProvider without coupling callers."""
    if settings.llm_provider == LLMProviderChoice.FILE:
        return FileExportImportProvider(settings.prompts_io_dir)
    if settings.llm_provider == LLMProviderChoice.GEMINI:
        return GeminiAPIProvider(settings)
    if settings.llm_provider == LLMProviderChoice.OLLAMA:
        return OllamaLocalProvider(settings)
    raise ConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}")
