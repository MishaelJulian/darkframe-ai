# Research and verification

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Build claim-level provenance and explicit uncertainty management.

## Detailed requirements
Each factual claim needs source URL, exact supporting excerpt or locator, publication/access date, source independence notes and status VERIFIED, DISPUTED or UNVERIFIED. Prefer primary sources and two independent supports for central claims. Do not invent citations or quotes. Flag sensitive real-person stories for manual review.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Block scripts with unsupported major claims. Research rights and licenses for every externally sourced asset; no copying creator expression.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
