# Model Provenance & Licensing Documentation

## 1. Local Image Generation Checkpoint: DreamShaper 8

- **Model Name:** DreamShaper 8 (`DreamShaper_8_pruned.safetensors`)
- **Author:** Lykon
- **Base Architecture:** Stable Diffusion v1.5 (`SD 1.5`, FP16 pruned with baked VAE)
- **Verification Date:** `2026-11-09`

### File Integrity & Source URLs
- **Download URL:** `https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors`
- **Hugging Face Repository:** `https://huggingface.co/Lykon/DreamShaper`
- **Civitai Canonical Page:** `https://civitai.com/models/4384/dreamshaper` (Model ID `4384`, Version ID `128713`)
- **Civitai Metadata API:** `https://civitai.com/api/v1/models/4384`
- **Exact File Size:** `2,132,625,894` bytes (`2.13 GB` / `1.986 GiB`)
- **Published SHA-256 Checksum (Verified identically on Hugging Face LFS and Civitai API):**
  `879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd`

### License & Commercial-Use Permissions (Recorded as Separate Fields)
> **Important Note:** The Hugging Face single-file repository (`Lykon/DreamShaper`) declares `license: other` in its model card metadata and defers to the canonical Civitai page (`https://civitai.com/models/4384/dreamshaper`). We do **not** treat Hugging Face's `license: other` tag as an explicit CreativeML Open RAIL-M grant on its own; instead, we record the repository license tag, the upstream base model license, and Civitai's explicit commercial-use permission flags as separate metadata fields.

| Metadata Field | Verified Value | Source |
| :--- | :--- | :--- |
| `license_id` | `"other"` | `https://huggingface.co/api/models/Lykon/DreamShaper` (`cardData.license`) |
| `base_model_license` | `"creativeml-openrail-m"` | Upstream SD 1.5 base (`runwayml/stable-diffusion-v1-5`) & `Lykon/dreamshaper-8` |
| `commercial_use_permissions` | `["Image", "RentCivit", "Rent"]` | `https://civitai.com/api/v1/models/4384` (`allowCommercialUse`) |
| `allow_no_credit` | `true` | `https://civitai.com/api/v1/models/4384` (`allowNoCredit`) |
| `allow_derivatives` | `true` | `https://civitai.com/api/v1/models/4384` (`allowDerivatives`) |
| `prohibited_commercial_uses` | Selling the model weights or merged checkpoint files directly (`"Sell"` is omitted from `allowCommercialUse`) | `https://civitai.com/api/v1/models/4384` |
| `ethical_use_restrictions` | Attachment A of CreativeML Open RAIL-M (no illegal content, no defamation/harassment of real individuals, no impersonation or deceptive factual fabrication) | CreativeML Open RAIL-M |

### Runtime & Hardware Verification (RTX 4050 6 GB VRAM)
- **Verified Local Launch Flags:** `--listen 127.0.0.1 --port 8188 --disable-auto-launch --disable-dynamic-vram`
- **Observed Generation Time (`512x768`, `batch_size=1`, `24` steps, `euler`/`normal`):** `11.58s` (cold model load included)
- **Observed GPU Memory (`nvidia-smi`):** `1,446 MiB` pre-generation → `3,462 MiB` post-generation (`2,459 MiB` free headroom out of `6,141 MiB` total VRAM; `torch_vram_total`: `2.00 GiB`, zero OOM)

---

## 2. Offline TTS Engine & Voice Model License Audit (Milestone M3)

- **Audit Date:** `2026-11-09`
- **Canonical Voice Repository Audited:** `https://huggingface.co/rhasspy/piper-voices` (`voices.json` + individual `MODEL_CARD` files across all 38 English `en_US` and `en_GB` voices)

### 2.1 Critical License Warning: Voices Excluded from Commercial Use
Although the repository root `rhasspy/piper-voices` carries a top-level `license: mit` tag on Hugging Face, individual voice models are governed by their **upstream training dataset licenses** and **base-checkpoint finetuning lineage**:
1. **`en_US-ryan-*` (`low`, `medium`, `high`) — EXCLUDED (`CC BY-NC-SA 4.0` Non-Commercial Only):**
   - Upstream dataset: [RyanSpeech (`https://arxiv.org/abs/2106.08468`)](https://arxiv.org/abs/2106.08468), licensed under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (`CC BY-NC-SA 4.0`)**. Cannot be used for monetized YouTube/Instagram channels.
2. **`en_US-lessac-*` and All Voices Finetuned from `lessac` — EXCLUDED (Academic / Non-Commercial Upstream):**
   - `en_US-lessac-*` is trained on the Blizzard Challenge 2013 Catherine Byers academic research dataset.
   - Furthermore, inspecting individual `MODEL_CARD` files confirmed that **`en_US-joe-medium`**, **`en_US-amy-medium`**, **`en_US-kusal-medium`**, **`en_US-l2arctic-medium`**, **`en_GB-alan-medium`**, **`en_GB-southern_english_male-low`**, and **`en_GB-northern_english_male-medium`** are all **finetuned from `en_US-lessac`** and therefore inherit its upstream academic restrictions.

### 2.2 Verified Commercial-Safe Public Domain Piper Voices (Pending User Approval Before Download)

The following voices were verified via their `MODEL_CARD` files in `https://huggingface.co/rhasspy/piper-voices` to be trained **from scratch** (or finetuned exclusively from another Public Domain LibriVox checkpoint) on **Public Domain LibriVox (`CC0 / Public Domain`)** recordings:

| Voice ID | Gender / Accent | Training Lineage | Upstream Dataset & License | ONNX File Size & MD5 | Config File Size & MD5 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`en_US-norman-medium`** *(Recommended Primary Male)* | US Male | **Trained from scratch** (1200 epochs, 15.5 hours, single speaker) | [LibriVox (`https://librivox.org`)](https://librivox.org) — **Public Domain** | `63,531,379` bytes (`60.59 MB`), MD5 `829cea515dc724d694b83b71e8083f9f` | `4,968` bytes, MD5 `975830d6f230f6eccf657d265de99eba` |
| **`en_US-john-medium`** *(Alternative US Male)* | US Male | Finetuned from `en_US-kristin` (both 100% LibriVox Public Domain) | [LibriVox (`https://librivox.org`)](https://librivox.org) — **Public Domain** | `63,201,294` bytes (`60.27 MB`), MD5 `89fda3dc2eb7fb0dc5ff7ceceaf4bb27` | `4,884` bytes, MD5 `4fcdecdabccdfb3f89bfdd4a4fdab871` |
| **`en_US-kristin-medium`** *(US Female)* | US Female | **Trained from scratch** (22 hours, single speaker) | [LibriVox (`https://librivox.org`)](https://librivox.org) — **Public Domain** | `63,201,294` bytes (`60.27 MB`), MD5 `b5effbc6cabcdedef15b79ffedbd8b25` | `4,967` bytes, MD5 `06fa12bd2cbffedcdbc30f9210772027` |
| **`en_GB-cori-medium`** *(UK Female)* | British Female | **Trained from scratch** (24 hours, single speaker) | [LibriVox (`https://librivox.org`)](https://librivox.org) — **Public Domain** | `63,201,294` bytes (`60.27 MB`), MD5 `be0ea1aa8edac853e3ce9b04a0112ab4` | `4,881` bytes, MD5 `fc5625641f648e91065445f4ef468674` |

### 2.3 Standalone Piper Binary License
- **Binary Package:** `piper_windows_amd64.zip` (`20,185,551` bytes / `19.25 MB`)
- **Release URL:** `https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip`
- **Source Repository & License:** `https://github.com/rhasspy/piper` — **MIT License** (Note: The standalone `rhasspy/piper` C++ release is MIT-licensed; newer `OHF-Voice/piper1-gpl` Python wheels switched to GPLv3, so using the standalone MIT binary via subprocess avoids GPLv3 copyleft coupling).


