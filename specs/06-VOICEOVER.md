# Voice and narration

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Offline TTS using an appropriately licensed voice/model; start with Piper or equivalent supported local engine.

## Detailed requirements
Generate wav narration, record voice/model provenance and actual duration. Avoid impersonating real narrators. Normalize loudness, preserve intelligibility and check clipping. Allow text segmentation and retries.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Produce narration.wav and word/segment timings; if alignment unavailable, flag approximate subtitle timing.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
