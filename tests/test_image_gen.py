"""Mocked HTTP and SQLite integration tests for Milestone M2 (ComfyUI local image generation)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from storytelling.config import Settings
from storytelling.db import DatabaseManager, GPUConcurrencyError
from storytelling.image_gen import (
    ComfyCheckpointMissingError,
    ComfyOOMError,
    ComfyResponseError,
    ComfyTimeoutError,
    ComfyUIClient,
    ComfyUnavailableError,
    ImageGenerationRequest,
    LocalImageGenerator,
    StylePolicyViolationError,
    build_sd15_txt2img_workflow,
    validate_prompt_style_policy,
)
from storytelling.models import EpisodeRecord, JobRecord, JobStatus, StoryRecord

FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdarkframe_test_png"


def _prepare_db_with_episode(tmp_path: Path, episode_id: str = "ep_01") -> DatabaseManager:
    db = DatabaseManager(tmp_path / "m2_test.db")
    db.apply_migrations()
    db.upsert_story(
        StoryRecord(
            story_id="st_01",
            title="The Abandoned Lighthouse",
            event_key="1900-lighthouse-mystery",
        )
    )
    db.upsert_episode(
        EpisodeRecord(
            episode_id=episode_id,
            story_id="st_01",
            series_index=1,
            title="Part 1: The Unlit Lamp",
        )
    )
    return db


def test_workflow_builder_uses_512x768_batch1_and_dark_style() -> None:
    wf = build_sd15_txt2img_workflow(
        checkpoint_name="v1-5-pruned-emaonly-fp16.safetensors",
        positive_prompt="A lone lantern on a wet stone pier at midnight",
        seed=101,
    )
    assert wf["4"]["inputs"]["ckpt_name"] == "v1-5-pruned-emaonly-fp16.safetensors"
    assert wf["5"]["inputs"]["width"] == 512
    assert wf["5"]["inputs"]["height"] == 768
    assert wf["5"]["inputs"]["batch_size"] == 1
    assert wf["3"]["inputs"]["seed"] == 101
    assert "dark 2d graphic novel illustration" in wf["6"]["inputs"]["text"]


def test_style_policy_blocks_living_artists_and_copyrighted_ip() -> None:
    with pytest.raises(StylePolicyViolationError, match="originality policy"):
        validate_prompt_style_policy("A dark alley in the style of Greg Rutkowski")

    with pytest.raises(StylePolicyViolationError, match="originality policy"):
        validate_prompt_style_policy("Batman standing on a gothic rooftop")

    with pytest.raises(StylePolicyViolationError, match="cannot be empty"):
        validate_prompt_style_policy("   ")


def test_comfy_unavailable_error_when_ports_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    client = ComfyUIClient(
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ComfyUnavailableError, match="unreachable"):
        client.detect_base_url()


def test_checkpoint_discovery_via_object_info_and_missing_checkpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"os": "nt"}})
        if request.url.path == "/models/checkpoints":
            return httpx.Response(404)
        if request.url.path == "/object_info":
            return httpx.Response(
                200,
                json={
                    "CheckpointLoaderSimple": {
                        "input": {
                            "required": {
                                "ckpt_name": [["v1-5-pruned-emaonly-fp16.safetensors"]]
                            }
                        }
                    }
                },
            )
        return httpx.Response(404)

    client = ComfyUIClient(
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(handler),
    )
    assert client.list_checkpoints() == ["v1-5-pruned-emaonly-fp16.safetensors"]
    assert (
        client.resolve_checkpoint("v1-5-pruned-emaonly-fp16.safetensors")
        == "v1-5-pruned-emaonly-fp16.safetensors"
    )
    with pytest.raises(ComfyCheckpointMissingError, match="not found"):
        client.resolve_checkpoint("non_existent_model.safetensors")


def test_empty_checkpoints_raises_missing_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"os": "nt"}})
        if request.url.path == "/models/checkpoints":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = ComfyUIClient(
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ComfyCheckpointMissingError, match="No checkpoints are installed"):
        client.resolve_checkpoint()


def test_invalid_json_and_timeout_handling() -> None:
    def bad_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-valid-json")

    bad_client = ComfyUIClient(
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(bad_json_handler),
    )
    with pytest.raises(ComfyResponseError, match="Invalid JSON"):
        bad_client.detect_base_url()

    def timeout_poll_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"os": "nt"}})
        if request.url.path == "/history/prompt_slow":
            return httpx.Response(200, json={})
        return httpx.Response(404)

    slow_client = ComfyUIClient(
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(timeout_poll_handler),
        poll_interval_sec=0.01,
        generation_timeout_sec=0.03,
    )
    with pytest.raises(ComfyTimeoutError, match="Timed out waiting"):
        slow_client.poll_history_and_extract_image_ref("prompt_slow")


def test_successful_image_generation_and_sqlite_persistence(tmp_path: Path) -> None:
    db = _prepare_db_with_episode(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"os": "nt"}})
        if request.url.path == "/models/checkpoints":
            return httpx.Response(200, json=["v1-5-pruned-emaonly-fp16.safetensors"])
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "pid_123"})
        if request.url.path == "/history/pid_123":
            return httpx.Response(
                200,
                json={
                    "pid_123": {
                        "status": {"status_str": "success", "messages": []},
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "ep_01_s00_0001.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                    }
                },
            )
        if request.url.path == "/view":
            return httpx.Response(200, content=FAKE_PNG_BYTES)
        return httpx.Response(404)

    settings = Settings(_env_file=None, output_dir=tmp_path / "output")
    client = ComfyUIClient(
        settings=settings,
        transport=httpx.MockTransport(handler),
        poll_interval_sec=0.01,
    )
    generator = LocalImageGenerator(settings=settings, db=db, client=client)

    result = generator.generate_scene_image(
        ImageGenerationRequest(
            episode_id="ep_01",
            scene_index=0,
            visual_prompt="An empty wooden dining table inside a coastal lighthouse",
            seed=777,
        )
    )

    assert result.width == 512
    assert result.height == 768
    assert result.oom_recovered is False
    assert result.image_path.exists()
    assert result.manifest_path.exists()
    assert result.image_path.read_bytes() == FAKE_PNG_BYTES

    assets = db.list_assets("ep_01")
    assert len(assets) == 1
    assert assets[0].sha256_checksum == result.sha256_checksum
    assert assets[0].license_id == "other"
    assert assets[0].metadata_json is not None
    assert assets[0].metadata_json["base_model_license"] == "creativeml-openrail-m"
    assert assets[0].metadata_json["commercial_use_permissions"] == [
        "Image",
        "RentCivit",
        "Rent",
    ]
    assert assets[0].metadata_json["allow_no_credit"] is True


def test_cuda_oom_triggers_vram_free_and_resolution_step_down(tmp_path: Path) -> None:
    db = _prepare_db_with_episode(tmp_path)
    submitted_resolutions: list[tuple[int, int]] = []
    free_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal free_called
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"os": "nt"}})
        if request.url.path == "/models/checkpoints":
            return httpx.Response(200, json=["v1-5-pruned-emaonly-fp16.safetensors"])
        if request.url.path == "/free":
            free_called = True
            return httpx.Response(200, json={"status": "freed"})
        if request.url.path == "/prompt":
            body = json.loads(request.content.decode("utf-8"))
            latent = body["prompt"]["5"]["inputs"]
            w, h = int(latent["width"]), int(latent["height"])
            submitted_resolutions.append((w, h))
            if (w, h) == (512, 768):
                return httpx.Response(200, json={"prompt_id": "pid_oom"})
            return httpx.Response(200, json={"prompt_id": "pid_ok"})
        if request.url.path == "/history/pid_oom":
            return httpx.Response(
                200,
                json={
                    "pid_oom": {
                        "status": {
                            "status_str": "error",
                            "messages": [
                                [
                                    "execution_error",
                                    {"exception_message": "torch.cuda.OutOfMemoryError: CUDA out of memory"},
                                ]
                            ],
                        }
                    }
                },
            )
        if request.url.path == "/history/pid_ok":
            return httpx.Response(
                200,
                json={
                    "pid_ok": {
                        "status": {"status_str": "success", "messages": []},
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "recovered.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                    }
                },
            )
        if request.url.path == "/view":
            return httpx.Response(200, content=FAKE_PNG_BYTES)
        return httpx.Response(404)

    settings = Settings(_env_file=None, output_dir=tmp_path / "output")
    client = ComfyUIClient(
        settings=settings,
        transport=httpx.MockTransport(handler),
        poll_interval_sec=0.01,
    )
    generator = LocalImageGenerator(settings=settings, db=db, client=client)

    result = generator.generate_scene_image(
        ImageGenerationRequest(
            episode_id="ep_01",
            scene_index=1,
            visual_prompt="A storm wave crashing against dark coastal cliffs",
            seed=888,
        )
    )
    assert free_called is True
    assert submitted_resolutions == [(512, 768), (448, 672)]
    assert (result.width, result.height) == (448, 672)
    assert result.oom_recovered is True


def test_persistent_oom_marks_job_failed_and_releases_gpu_lock(tmp_path: Path) -> None:
    db = _prepare_db_with_episode(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"os": "nt"}})
        if request.url.path == "/models/checkpoints":
            return httpx.Response(200, json=["v1-5-pruned-emaonly-fp16.safetensors"])
        if request.url.path == "/free":
            return httpx.Response(200, json={"status": "freed"})
        if request.url.path == "/prompt":
            return httpx.Response(
                500,
                json={"error": "CUDA error: out of memory"},
            )
        return httpx.Response(404)

    settings = Settings(_env_file=None, output_dir=tmp_path / "output")
    client = ComfyUIClient(
        settings=settings,
        transport=httpx.MockTransport(handler),
    )
    generator = LocalImageGenerator(settings=settings, db=db, client=client)

    with pytest.raises(ComfyOOMError, match="persisted across all fallback resolutions"):
        generator.generate_scene_image(
            ImageGenerationRequest(
                episode_id="ep_01",
                scene_index=2,
                visual_prompt="An iron key resting on a weathered journal",
                seed=999,
            )
        )

    # Confirm the failed job released the GPU lock so a subsequent GPU job can start
    next_job = db.register_job(
        JobRecord(
            job_id="job_after_oom",
            job_key="ep_01:image:scene_03:seed_1",
            episode_id="ep_01",
            stage="IMAGE_GENERATION",
            uses_gpu=True,
        )
    )
    started = db.start_job(next_job.job_key)
    assert started.status == JobStatus.RUNNING

    # And while `started` is RUNNING, starting another image generation must be blocked
    with pytest.raises(GPUConcurrencyError):
        generator.generate_scene_image(
            ImageGenerationRequest(
                episode_id="ep_01",
                scene_index=4,
                visual_prompt="A foggy harbor pier at dusk",
                seed=111,
            )
        )
