# Story discovery

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Collect candidate real-world events from permitted official/public endpoints and curated source lists; comply with robots, licensing, rate limits and attribution.

## Detailed requirements
Normalize title, date, location (when relevant), original source URL, source type, retrieval time and confidence. Deduplicate by event, not just title. Never assume a viral retelling is an independent source.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Output candidate JSON and ranked queue; add fixture-driven tests and a no-network mode.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
