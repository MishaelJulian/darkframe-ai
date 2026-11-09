# Budget and resource controls

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Additional software/API spending target ₹0 during 14-day local trial.

## Detailed requirements
Track GPU time, generation duration, storage use, optional API spend, failed generations and output count. Limit concurrent GPU jobs to one on 6 GB VRAM. Prefer open-source local components and commercially permitted models.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Enforce no paid API calls by default; explicit opt-in and per-job/monthly rupee limits if paid services are later introduced.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
