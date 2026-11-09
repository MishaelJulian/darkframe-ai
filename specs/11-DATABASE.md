# Data model

> Status: planning specification. Confirm assumptions before implementation.

## Objective
SQLite database with migrations, foreign keys and WAL mode for local single-machine operation.

## Detailed requirements
Tables: stories, sources, claims, claim_sources, episodes, scenes, assets, jobs, quality_checks, publish_records. Unique IDs, statuses, timestamps, rights provenance and model/version tracking.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Provide migrations, indexes, backup/restore procedure and fixtures; keep binary assets on disk referenced by path and checksum.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
