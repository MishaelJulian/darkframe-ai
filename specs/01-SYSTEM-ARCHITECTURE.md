# System architecture

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Python 3.11+ modular pipeline with SQLite, structured JSON contracts, local ComfyUI HTTP API, local TTS, FFmpeg, and optional later n8n.

## Detailed requirements
Modules: discovery -> evidence -> story planning -> scripts -> scenes -> images -> voice -> edit -> QC -> publishing. Every module must be rerunnable and idempotent, with stable story_id, episode_id, job_id, artifact hashes, and state transitions.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Document CLI, module boundaries, config, structured logs, retries, and failure queues. No cloud services required for the MVP.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
