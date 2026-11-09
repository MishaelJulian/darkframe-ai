"""ComfyUI local HTTP client, dark 2D workflow builder, OOM recovery, and asset persistence."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from storytelling.config import Settings, StylePresetChoice
from storytelling.db import DatabaseManager
from storytelling.models import AssetRecord, AssetType, JobRecord, utc_now_iso

# Resolution ladder optimized for RTX 4050 (6 GB VRAM), starting at 512x768 (batch=1)
VRAM_SAFE_RESOLUTIONS: tuple[tuple[int, int], ...] = (
    (512, 768),
    (448, 672),
    (384, 576),
)


class DarkStylePresetConfig(BaseModel):
    """Configuration for a specific dark 2D visual style preset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    preset_id: StylePresetChoice
    positive_prefix: str
    positive_suffix: str
    negative_prompt: str


STYLE_PRESETS: dict[StylePresetChoice, DarkStylePresetConfig] = {
    StylePresetChoice.INKED_GRAPHIC_NOVEL: DarkStylePresetConfig(
        preset_id=StylePresetChoice.INKED_GRAPHIC_NOVEL,
        positive_prefix=(
            "(2d graphic novel illustration:1.25), (bold black ink outlines, strong cel shading:1.2), "
            "comic book ink linework, limited muted color palette, simplified geometric shapes, "
            "dramatic comic-book chiaroscuro shadows, flat color fills"
        ),
        positive_suffix="hand-inked 2d comic panel, non-photorealistic, original 2d illustration",
        negative_prompt=(
            "photorealistic, photograph, photo, 3d render, cgi, unreal engine, octane render, "
            "camera lens, depth of field, bokeh, soft airbrush, smooth 3d shading, bright neon, "
            "oversaturated, watermark, text, logo, signature, blurry, low quality, deformed hands, "
            "extra limbs, cropped"
        ),
    ),
    StylePresetChoice.ILLUSTRATED_NOIR: DarkStylePresetConfig(
        preset_id=StylePresetChoice.ILLUSTRATED_NOIR,
        positive_prefix=(
            "(hand-drawn noir illustration:1.25), (textured ink and charcoal shadows:1.2), "
            "stylized mystery book illustration, muted slate teal and amber palette, "
            "stylized hand-painted background, visible pen and crosshatching strokes, "
            "cinematic noir composition"
        ),
        positive_suffix="stylized 2d noir artwork, non-photorealistic, original hand-drawn illustration",
        negative_prompt=(
            "photorealistic, photograph, raw photo, dslr, 3d render, cgi, glossy plastic, "
            "anime, bright neon, oversaturated, watermark, text, logo, signature, blurry, "
            "low quality, deformed hands, extra limbs, cropped"
        ),
    ),
    StylePresetChoice.DARK_2D_ANIMATION: DarkStylePresetConfig(
        preset_id=StylePresetChoice.DARK_2D_ANIMATION,
        positive_prefix=(
            "(flat-shaded 2d animated film frame:1.25), (2d hand-drawn animation cel:1.2), "
            "simplified stylized shapes, clear dark silhouettes, clean 2d linework, "
            "atmospheric rim lighting, matte painted 2d background, dark animated thriller aesthetic"
        ),
        positive_suffix="2d animation cel shading, non-photorealistic, original 2d animated art",
        negative_prompt=(
            "photorealistic, photograph, live action, 3d render, cgi, pixar, blender, "
            "oil painting impastos, heavy sketch crosshatching, bright neon, watermark, "
            "text, logo, signature, blurry, low quality, deformed hands, extra limbs, cropped"
        ),
    ),
}

DEFAULT_DARK_2D_NEGATIVE_PROMPT = STYLE_PRESETS[
    StylePresetChoice.INKED_GRAPHIC_NOVEL
].negative_prompt

# Forbidden phrases to prevent living-artist imitation or copyrighted character/IP styles
FORBIDDEN_STYLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bin the style of\b", re.IGNORECASE),
    re.compile(r"\bstyle of [a-z]+", re.IGNORECASE),
    re.compile(r"\bby artist\b", re.IGNORECASE),
    re.compile(r"\bart by\b", re.IGNORECASE),
    re.compile(
        r"\b(marvel|dc comics|batman|spider-man|superman|disney|pixar|studio ghibli|"
        r"mignola|junji ito|greg rutkowski|moebius|kentaro miura)\b",
        re.IGNORECASE,
    ),
)


class ComfyUIError(RuntimeError):
    """Base exception for ComfyUI local generation errors."""


class ComfyUnavailableError(ComfyUIError):
    """Raised when the local ComfyUI HTTP server is unreachable."""


class ComfyCheckpointMissingError(ComfyUIError):
    """Raised when no SD 1.5 checkpoint is installed or the requested checkpoint is absent."""


class ComfyTimeoutError(ComfyUIError):
    """Raised when ComfyUI request or polling exceeds timeout."""


class ComfyResponseError(ComfyUIError):
    """Raised when ComfyUI returns malformed JSON or a non-OOM node execution error."""


class ComfyOOMError(ComfyUIError):
    """Raised when CUDA Out-Of-Memory persists across all fallback resolutions."""


class StylePolicyViolationError(ValueError):
    """Raised when a visual prompt references forbidden artist imitation or copyrighted IP."""


class ImageGenerationRequest(BaseModel):
    """Typed request contract for generating a single vertical scene illustration."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    scene_id: str | None = None
    scene_index: int = Field(default=0, ge=0)
    visual_prompt: str
    style_preset: StylePresetChoice = StylePresetChoice.INKED_GRAPHIC_NOVEL
    negative_prompt: str | None = None
    checkpoint_name: str | None = None
    license_id: str = "other"
    base_model_license: str = "creativeml-openrail-m"
    commercial_use_permissions: list[str] = Field(
        default_factory=lambda: ["Image", "RentCivit", "Rent"]
    )
    allow_no_credit: bool = True
    license_source_urls: list[str] = Field(
        default_factory=lambda: [
            "https://huggingface.co/Lykon/DreamShaper",
            "https://civitai.com/models/4384/dreamshaper",
            "https://civitai.com/api/v1/models/4384",
        ]
    )
    license_verified_at: str = "2026-11-09"
    rights_provenance: str = (
        "Local ComfyUI generation; commercial use of generated images permitted "
        "per Civitai allowCommercialUse=['Image'] (model ID 4384, v8)"
    )
    seed: int = Field(default=42, ge=0)
    width: int = Field(default=512, ge=256, le=1024)
    height: int = Field(default=768, ge=256, le=1024)
    steps: int = Field(default=24, ge=1, le=50)
    cfg: float = Field(default=7.0, ge=1.0, le=20.0)
    sampler_name: str = "euler"
    scheduler: str = "normal"


class ImageGenerationResult(BaseModel):
    """Typed output contract for a completed local image generation."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    job_key: str
    style_preset: StylePresetChoice
    image_path: Path
    manifest_path: Path
    sha256_checksum: str
    byte_size: int
    checkpoint_name: str
    license_id: str
    seed: int
    width: int
    height: int
    oom_recovered: bool = False
    gpu_seconds: float = 0.0


def validate_prompt_style_policy(prompt: str) -> str:
    """Ensure prompt does not imitate living artists or use copyrighted IP styles."""
    cleaned = prompt.strip()
    if not cleaned:
        raise StylePolicyViolationError("Visual prompt cannot be empty.")
    for pattern in FORBIDDEN_STYLE_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            raise StylePolicyViolationError(
                f"Visual prompt violates originality policy near '{match.group(0)}'. "
                "Do not imitate specific artists or copyrighted characters/franchises."
            )
    return cleaned


def compose_dark_2d_prompt(
    scene_description: str,
    style_preset: StylePresetChoice = StylePresetChoice.INKED_GRAPHIC_NOVEL,
) -> str:
    """Validate scene description and place style-defining tokens at the beginning of the prompt."""
    validated = validate_prompt_style_policy(scene_description)
    preset_cfg = STYLE_PRESETS[style_preset]
    if validated.lower().startswith(preset_cfg.positive_prefix.lower()):
        return validated
    return f"{preset_cfg.positive_prefix}, {validated}, {preset_cfg.positive_suffix}"


def resolve_negative_prompt(
    style_preset: StylePresetChoice = StylePresetChoice.INKED_GRAPHIC_NOVEL,
    custom_negative_prompt: str | None = None,
) -> str:
    """Return preset negative prompt unless overridden."""
    if custom_negative_prompt is not None and custom_negative_prompt.strip():
        return custom_negative_prompt.strip()
    return STYLE_PRESETS[style_preset].negative_prompt


def build_sd15_txt2img_workflow(
    *,
    checkpoint_name: str,
    positive_prompt: str,
    style_preset: StylePresetChoice = StylePresetChoice.INKED_GRAPHIC_NOVEL,
    negative_prompt: str | None = None,
    seed: int = 42,
    width: int = 512,
    height: int = 768,
    steps: int = 24,
    cfg: float = 7.0,
    sampler_name: str = "euler",
    scheduler: str = "normal",
    filename_prefix: str = "darkframe_scene",
) -> dict[str, Any]:
    """Build a deterministic ComfyUI API prompt workflow for SD 1.5 (batch size = 1)."""
    styled_positive = compose_dark_2d_prompt(positive_prompt, style_preset=style_preset)
    effective_negative = resolve_negative_prompt(style_preset, negative_prompt)
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": cfg,
                "denoise": 1.0,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "seed": seed,
                "steps": steps,
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": checkpoint_name,
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": height,
                "width": width,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": styled_positive,
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": effective_negative,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": ["8", 0],
            },
        },
    }


def _is_oom_message(text: str) -> bool:
    lowered = text.lower()
    return (
        "out of memory" in lowered
        or "cuda error: out of memory" in lowered
        or "torch.cuda.outofmemoryerror" in lowered
        or "allocation on device" in lowered
    )


class ComfyUIClient:
    """Typed HTTP client for local ComfyUI Desktop API on RTX 4050 (6 GB VRAM)."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        timeout_sec: float = 10.0,
        poll_interval_sec: float = 0.5,
        generation_timeout_sec: float = 180.0,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.generation_timeout_sec = generation_timeout_sec
        self._active_base_url: str | None = None

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport, timeout=self.timeout_sec)

    def _candidate_base_urls(self) -> list[str]:
        host = self.settings.comfyui_host
        ports = [self.settings.comfyui_port]
        if self.settings.comfyui_fallback_port not in ports:
            ports.append(self.settings.comfyui_fallback_port)
        return [f"http://{host}:{p}" for p in ports]

    def detect_base_url(self) -> str:
        """Detect active ComfyUI HTTP port via `/system_stats`."""
        if self._active_base_url is not None:
            return self._active_base_url

        errors: list[str] = []
        with self._client() as client:
            for base_url in self._candidate_base_urls():
                try:
                    resp = client.get(f"{base_url}/system_stats")
                    resp.raise_for_status()
                    data = resp.json()
                    if not isinstance(data, dict) or "system" not in data:
                        raise ComfyResponseError(
                            f"Unexpected /system_stats payload from {base_url}"
                        )
                    self._active_base_url = base_url
                    return base_url
                except httpx.TimeoutException as exc:
                    errors.append(f"{base_url} (timeout: {exc})")
                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    errors.append(f"{base_url} ({exc})")
                except ValueError as exc:
                    raise ComfyResponseError(
                        f"Invalid JSON from {base_url}/system_stats: {exc}"
                    ) from exc

        raise ComfyUnavailableError(
            "Local ComfyUI HTTP API is unreachable. Checked: " + "; ".join(errors)
        )

    def list_checkpoints(self) -> list[str]:
        """Query `/models/checkpoints` with fallback to `/object_info` runtime contract."""
        base_url = self.detect_base_url()
        with self._client() as client:
            try:
                resp = client.get(f"{base_url}/models/checkpoints")
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, list) and all(
                        isinstance(item, str) for item in payload
                    ):
                        return payload
            except httpx.TimeoutException as exc:
                raise ComfyTimeoutError(
                    f"Timed out querying {base_url}/models/checkpoints: {exc}"
                ) from exc
            except ValueError as exc:
                raise ComfyResponseError(
                    f"Malformed JSON from {base_url}/models/checkpoints: {exc}"
                ) from exc
            except httpx.RequestError as exc:
                raise ComfyUnavailableError(
                    f"Connection lost querying {base_url}/models/checkpoints: {exc}"
                ) from exc

            # Fallback to /object_info/CheckpointLoaderSimple or /object_info
            try:
                info_resp = client.get(f"{base_url}/object_info")
                info_resp.raise_for_status()
                info_data = info_resp.json()
            except httpx.TimeoutException as exc:
                raise ComfyTimeoutError(
                    f"Timed out querying {base_url}/object_info: {exc}"
                ) from exc
            except (ValueError, KeyError, TypeError) as exc:
                raise ComfyResponseError(
                    f"Malformed JSON from {base_url}/object_info: {exc}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ComfyResponseError(
                    f"HTTP error from {base_url}/object_info: {exc}"
                ) from exc

            try:
                ckpt_field = info_data["CheckpointLoaderSimple"]["input"]["required"][
                    "ckpt_name"
                ][0]
                if isinstance(ckpt_field, list):
                    return [str(x) for x in ckpt_field]
            except (KeyError, IndexError, TypeError) as exc:
                raise ComfyResponseError(
                    "Could not extract CheckpointLoaderSimple.ckpt_name from /object_info"
                ) from exc

        return []

    def resolve_checkpoint(self, requested: str | None = None) -> str:
        """Select a verified installed checkpoint or raise ComfyCheckpointMissingError."""
        installed = self.list_checkpoints()
        if not installed:
            raise ComfyCheckpointMissingError(
                "No checkpoints are installed in ComfyUI. Install an approved SD 1.5 "
                ".safetensors checkpoint before generating images."
            )
        if requested is not None:
            if requested not in installed:
                raise ComfyCheckpointMissingError(
                    f"Requested checkpoint '{requested}' not found. Installed: {installed}"
                )
            return requested
        return installed[0]

    def free_vram(self) -> bool:
        """Ask ComfyUI `/free` endpoint to unload models and clear CUDA cache."""
        base_url = self.detect_base_url()
        with self._client() as client:
            try:
                resp = client.post(
                    f"{base_url}/free",
                    json={"unload_models": True, "free_memory": True},
                )
                return resp.status_code == 200
            except httpx.HTTPError:
                return False

    def submit_prompt(self, workflow: dict[str, Any]) -> str:
        """Submit workflow to `/prompt` and return `prompt_id`."""
        base_url = self.detect_base_url()
        with self._client() as client:
            try:
                resp = client.post(
                    f"{base_url}/prompt",
                    json={"prompt": workflow, "client_id": "darkframe-storytelling"},
                )
            except httpx.TimeoutException as exc:
                raise ComfyTimeoutError(
                    f"Timed out submitting workflow to {base_url}/prompt: {exc}"
                ) from exc
            except httpx.RequestError as exc:
                raise ComfyUnavailableError(
                    f"Failed connecting to {base_url}/prompt: {exc}"
                ) from exc

            try:
                payload = resp.json()
            except ValueError as exc:
                raise ComfyResponseError(
                    f"Invalid JSON from /prompt (status {resp.status_code})"
                ) from exc

            if resp.status_code >= 400:
                err_str = json.dumps(payload)
                if _is_oom_message(err_str):
                    raise ComfyOOMError(f"CUDA OOM during /prompt submission: {err_str}")
                raise ComfyResponseError(
                    f"ComfyUI rejected /prompt ({resp.status_code}): {err_str}"
                )

            prompt_id = payload.get("prompt_id") if isinstance(payload, dict) else None
            if not prompt_id or not isinstance(prompt_id, str):
                raise ComfyResponseError(
                    f"Missing prompt_id in ComfyUI /prompt response: {payload}"
                )
            return prompt_id

    def poll_history_and_extract_image_ref(self, prompt_id: str) -> dict[str, str]:
        """Poll `/history/{prompt_id}` until completion and return output image reference."""
        base_url = self.detect_base_url()
        deadline = time.monotonic() + self.generation_timeout_sec
        with self._client() as client:
            while time.monotonic() < deadline:
                try:
                    resp = client.get(f"{base_url}/history/{prompt_id}")
                    resp.raise_for_status()
                    history_data = resp.json()
                except httpx.TimeoutException as exc:
                    raise ComfyTimeoutError(
                        f"Timed out polling /history/{prompt_id}: {exc}"
                    ) from exc
                except ValueError as exc:
                    raise ComfyResponseError(
                        f"Invalid JSON in /history/{prompt_id}: {exc}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise ComfyResponseError(
                        f"HTTP error polling /history/{prompt_id}: {exc}"
                    ) from exc

                if isinstance(history_data, dict) and prompt_id in history_data:
                    entry = history_data[prompt_id]
                    status_block = entry.get("status", {}) if isinstance(entry, dict) else {}
                    status_str = status_block.get("status_str", "")
                    messages = status_block.get("messages", [])
                    msg_dump = json.dumps(messages)
                    if status_str == "error" or "execution_error" in msg_dump:
                        if _is_oom_message(msg_dump):
                            raise ComfyOOMError(
                                f"CUDA Out-Of-Memory executing prompt {prompt_id}: {msg_dump}"
                            )
                        raise ComfyResponseError(
                            f"ComfyUI execution error for {prompt_id}: {msg_dump}"
                        )

                    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
                    for node_output in outputs.values():
                        images = (
                            node_output.get("images", [])
                            if isinstance(node_output, dict)
                            else []
                        )
                        if images and isinstance(images[0], dict):
                            img_info = images[0]
                            if "filename" in img_info:
                                return {
                                    "filename": str(img_info["filename"]),
                                    "subfolder": str(img_info.get("subfolder", "")),
                                    "type": str(img_info.get("type", "output")),
                                }
                time.sleep(self.poll_interval_sec)

        raise ComfyTimeoutError(
            f"Timed out waiting {self.generation_timeout_sec}s for prompt_id={prompt_id}"
        )

    def fetch_image_bytes(
        self, filename: str, subfolder: str = "", folder_type: str = "output"
    ) -> bytes:
        """Download generated image bytes from `/view`."""
        base_url = self.detect_base_url()
        with self._client() as client:
            try:
                resp = client.get(
                    f"{base_url}/view",
                    params={
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": folder_type,
                    },
                )
                resp.raise_for_status()
            except httpx.TimeoutException as exc:
                raise ComfyTimeoutError(
                    f"Timed out fetching image {filename} from /view: {exc}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ComfyResponseError(
                    f"Failed fetching image {filename} from /view: {exc}"
                ) from exc

            if not resp.content:
                raise ComfyResponseError(f"Empty image payload returned for {filename}")
            return resp.content


class LocalImageGenerator:
    """High-level service coordinating GPU-serialized ComfyUI image generation and SQLite persistence."""

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        client: ComfyUIClient,
    ) -> None:
        self.settings = settings
        self.db = db
        self.client = client

    def _resolution_ladder(self, initial_width: int, initial_height: int) -> list[tuple[int, int]]:
        ladder: list[tuple[int, int]] = [(initial_width, initial_height)]
        for res in VRAM_SAFE_RESOLUTIONS:
            if res not in ladder and (
                res[0] <= initial_width and res[1] <= initial_height
            ):
                ladder.append(res)
        return ladder

    def generate_scene_image(
        self, request: ImageGenerationRequest, output_dir: Path | None = None
    ) -> ImageGenerationResult:
        """Generate a vertical dark 2D scene image with GPU locking and automatic OOM fallback."""
        styled_prompt = compose_dark_2d_prompt(
            request.visual_prompt, style_preset=request.style_preset
        )
        effective_negative = resolve_negative_prompt(
            request.style_preset, request.negative_prompt
        )

        job_key = (
            f"{request.episode_id}:image:scene_{request.scene_index:02d}:"
            f"{request.style_preset.value}:{request.width}x{request.height}:seed_{request.seed}"
        )
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self.db.register_job(
            JobRecord(
                job_id=job_id,
                job_key=job_key,
                episode_id=request.episode_id,
                stage="IMAGE_GENERATION",
                uses_gpu=True,
            )
        )
        self.db.start_job(job_key)
        start_time = time.monotonic()

        try:
            ckpt = self.client.resolve_checkpoint(request.checkpoint_name)
            ladder = self._resolution_ladder(request.width, request.height)
            oom_recovered = False
            last_oom: ComfyOOMError | None = None

            for attempt_idx, (width, height) in enumerate(ladder):
                workflow = build_sd15_txt2img_workflow(
                    checkpoint_name=ckpt,
                    positive_prompt=request.visual_prompt,
                    style_preset=request.style_preset,
                    negative_prompt=effective_negative,
                    seed=request.seed,
                    width=width,
                    height=height,
                    steps=request.steps,
                    cfg=request.cfg,
                    sampler_name=request.sampler_name,
                    scheduler=request.scheduler,
                    filename_prefix=(
                        f"{request.episode_id}_s{request.scene_index:02d}_"
                        f"{request.style_preset.value.lower()}"
                    ),
                )
                try:
                    prompt_id = self.client.submit_prompt(workflow)
                    img_ref = self.client.poll_history_and_extract_image_ref(prompt_id)
                    img_bytes = self.client.fetch_image_bytes(
                        filename=img_ref["filename"],
                        subfolder=img_ref["subfolder"],
                        folder_type=img_ref["type"],
                    )
                    if attempt_idx > 0:
                        oom_recovered = True
                    break
                except ComfyOOMError as oom_err:
                    last_oom = oom_err
                    self.client.free_vram()
            else:
                raise ComfyOOMError(
                    f"CUDA OOM persisted across all fallback resolutions {ladder}: {last_oom}"
                )

            target_dir = (output_dir or self.settings.output_dir) / request.episode_id / "images"
            target_dir.mkdir(parents=True, exist_ok=True)
            stem = (
                f"scene_{request.scene_index:02d}_{request.style_preset.value}_"
                f"{width}x{height}_seed_{request.seed}"
            )
            image_path = target_dir / f"{stem}.png"
            manifest_path = target_dir / f"{stem}.manifest.json"

            image_path.write_bytes(img_bytes)
            sha256_hex = hashlib.sha256(img_bytes).hexdigest()
            byte_size = len(img_bytes)
            gpu_seconds = round(max(0.0, time.monotonic() - start_time), 3)

            manifest_payload: dict[str, Any] = {
                "episode_id": request.episode_id,
                "scene_id": request.scene_id,
                "scene_index": request.scene_index,
                "style_preset": request.style_preset.value,
                "prompt_id": prompt_id,
                "checkpoint_name": ckpt,
                "license_id": request.license_id,
                "base_model_license": request.base_model_license,
                "commercial_use_permissions": request.commercial_use_permissions,
                "allow_no_credit": request.allow_no_credit,
                "license_source_urls": request.license_source_urls,
                "license_verified_at": request.license_verified_at,
                "rights_provenance": request.rights_provenance,
                "raw_scene_prompt": request.visual_prompt,
                "positive_prompt": styled_prompt,
                "negative_prompt": effective_negative,
                "seed": request.seed,
                "requested_resolution": [request.width, request.height],
                "actual_resolution": [width, height],
                "oom_recovered": oom_recovered,
                "steps": request.steps,
                "cfg": request.cfg,
                "sampler_name": request.sampler_name,
                "scheduler": request.scheduler,
                "sha256_checksum": sha256_hex,
                "byte_size": byte_size,
                "gpu_seconds": gpu_seconds,
                "workflow": workflow,
                "created_at": utc_now_iso(),
            }
            manifest_path.write_text(
                json.dumps(manifest_payload, indent=2), encoding="utf-8"
            )

            asset_id = f"ast_{uuid.uuid4().hex[:12]}"
            self.db.record_asset(
                AssetRecord(
                    asset_id=asset_id,
                    episode_id=request.episode_id,
                    scene_id=request.scene_id,
                    asset_type=AssetType.IMAGE,
                    file_path=str(image_path),
                    sha256_checksum=sha256_hex,
                    byte_size=byte_size,
                    model_name=ckpt,
                    model_version="sd1.5",
                    license_id=request.license_id,
                    rights_provenance=request.rights_provenance,
                    metadata_json=manifest_payload,
                )
            )
            self.db.complete_job(job_key, gpu_seconds=gpu_seconds)

            return ImageGenerationResult(
                asset_id=asset_id,
                job_key=job_key,
                style_preset=request.style_preset,
                image_path=image_path,
                manifest_path=manifest_path,
                sha256_checksum=sha256_hex,
                byte_size=byte_size,
                checkpoint_name=ckpt,
                license_id=request.license_id,
                seed=request.seed,
                width=width,
                height=height,
                oom_recovered=oom_recovered,
                gpu_seconds=gpu_seconds,
            )
        except Exception as exc:
            elapsed = round(max(0.0, time.monotonic() - start_time), 3)
            self.db.fail_job(job_key, error_message=str(exc), gpu_seconds=elapsed)
            raise
