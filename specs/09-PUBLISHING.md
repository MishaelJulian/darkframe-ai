# Publishing integration

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Implement as a disabled-by-default adapter for official YouTube and Meta APIs only after credentials, eligibility and review gates are configured.

## Detailed requirements
Keep platform-specific authentication separate. Handle refresh tokens securely, rate limits, upload processing, retry without duplicates, platform metadata and synthetic-content disclosure where required. Never assume posting access from a personal account.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
MVP is export-only. Publishing must require explicit enablement and dry-run tests; no credentials in git.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
