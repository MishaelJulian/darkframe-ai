# Quality control

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Gate production and publishing on evidence, originality, assets, audio/video and episode continuity.

## Detailed requirements
Automated checks: factual claim references resolve; no forbidden unlicensed assets; unique story angle; no repetitive filler; correct duration, loudness, captions, frame size; no missing scenes. Human review required for sensitive/uncertain cases.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Produce qc_report.json with PASS, FAIL, REVIEW and clear reasons. Never treat an LLM score as factual proof.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
