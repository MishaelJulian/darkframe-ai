# Testing and acceptance

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Use pytest, mocked HTTP responses and deterministic fixture stories to test contracts.

## Detailed requirements
Test empty discovery, duplicate stories, missing citations, conflicting sources, bad JSON, absent checkpoint, API unavailable, GPU OOM, TTS failure, ffmpeg missing, interrupted jobs, duplicate uploads, rights rejection.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Acceptance: one locally generated image, one narrated test clip, one reviewed 60-second episode, then four linked episodes, all with reproducible manifests.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
