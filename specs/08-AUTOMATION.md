# Job orchestration

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Use Python CLI scheduler initially; optional n8n after reliable local production.

## Detailed requirements
Persistent state machine DISCOVERED, RESEARCHING, NEEDS_REVIEW, APPROVED, SCRIPTED, ASSETS_READY, RENDERED, QC_PASSED, PUBLISHED, FAILED. Retries with exponential backoff and capped attempt counts; dedupe job keys and preserve episode order.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Do not auto-publish on uncertain facts, rights or failed technical checks. Pause safely when PC sleeps or is off.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
