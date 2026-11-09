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
