"""Tests for typed configuration, safety guards, and LLM provider factory."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from storytelling.config import LLMProviderChoice, Settings
from storytelling.llm_base import (
    FileExportImportProvider,
    GeminiAPIProvider,
    LLMRequest,
    OllamaLocalProvider,
    PendingManualResponseError,
    create_llm_provider,
)


def test_default_settings_are_safe() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_provider == LLMProviderChoice.FILE
    assert settings.allow_paid_apis is False
    assert settings.allow_gemini_api is False
    assert settings.publishing_enabled is False
    assert settings.max_concurrent_gpu_jobs == 1
    assert settings.monthly_budget_inr == 0.0
    assert settings.per_job_budget_inr == 0.0


def test_reject_multiple_concurrent_gpu_jobs() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_concurrent_gpu_jobs=2)


def test_reject_paid_budget_when_paid_apis_disabled() -> None:
    with pytest.raises(ValidationError, match="ALLOW_PAID_APIS=true"):
        Settings(_env_file=None, allow_paid_apis=False, monthly_budget_inr=100.0)


def test_reject_gemini_provider_without_opt_in_or_key() -> None:
    with pytest.raises(ValidationError, match="ALLOW_GEMINI_API=true"):
        Settings(
            _env_file=None,
            llm_provider=LLMProviderChoice.GEMINI,
            allow_gemini_api=False,
        )

    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(
            _env_file=None,
            llm_provider=LLMProviderChoice.GEMINI,
            allow_gemini_api=True,
            gemini_api_key=SecretStr(""),
        )


def test_llm_provider_switching_and_file_export_import(tmp_path: Path) -> None:
    file_settings = Settings(
        _env_file=None,
        llm_provider=LLMProviderChoice.FILE,
        prompts_io_dir=tmp_path / "prompts",
    )
    provider = create_llm_provider(file_settings)
    assert isinstance(provider, FileExportImportProvider)

    req = LLMRequest(
        request_id="ep01_plan",
        task_type="episode_plan",
        system_prompt="You are an original dark mystery architect.",
        user_prompt="Plan a 60s episode grounded in claim_01.",
        expected_schema_name="EpisodePlan",
        expected_json_schema={"type": "object", "properties": {"hook": {"type": "string"}}},
    )

    with pytest.raises(PendingManualResponseError):
        provider.generate_structured(req)

    assert provider.request_path("ep01_plan").exists()
    assert provider.prompt_markdown_path("ep01_plan").exists()

    # Simulate user pasting validated JSON response
    provider.response_path("ep01_plan").write_text(
        '{"hook": "In 1900, three lighthouse keepers vanished without a trace."}',
        encoding="utf-8",
    )
    resp = provider.generate_structured(req)
    assert resp.provider == LLMProviderChoice.FILE
    assert "lighthouse" in resp.structured_output["hook"]

    # Verify Gemini and Ollama provider instantiation via config switch
    gemini_settings = Settings(
        _env_file=None,
        llm_provider=LLMProviderChoice.GEMINI,
        allow_gemini_api=True,
        gemini_api_key=SecretStr("test-dummy-key"),
    )
    assert isinstance(create_llm_provider(gemini_settings), GeminiAPIProvider)

    ollama_settings = Settings(_env_file=None, llm_provider=LLMProviderChoice.OLLAMA)
    assert isinstance(create_llm_provider(ollama_settings), OllamaLocalProvider)
