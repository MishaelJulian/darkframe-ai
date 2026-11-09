# ComfyUI local images

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Use ComfyUI Desktop v0.44.2 local NVIDIA instance on RTX 4050 6 GB VRAM and 24 GB RAM.

## Detailed requirements
Detect API host/port, query /object_info and /models/checkpoints where supported, submit /prompt, poll /history/{prompt_id}, fetch /view. Verify actual API contract at runtime. Do not assume any checkpoint is installed. Start SD 1.5-compatible checkpoint with commercial rights, 512x768 or 576x1024 if memory allows, batch size 1, 20–28 steps. Save seed, model license, prompt, workflow JSON and output metadata.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
No paid endpoints. Do not download model weights or execute installers without approval. Recover from OOM by reducing resolution and clearing job state; never silently switch to cloud.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
