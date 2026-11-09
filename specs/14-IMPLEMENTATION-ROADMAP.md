# Build milestones

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Work in vertical slices and ask for approval before heavy downloads, installs, paid calls or publishing.

## Detailed requirements
M0 inspect machine and ComfyUI API; M1 create repo/config/SQLite/tests; M2 local image proof; M3 voice + FFmpeg proof; M4 research and claim evidence; M5 story engine; M6 full single episode; M7 four-episode continuity; M8 scheduling; M9 publishing adapter.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
At each milestone produce code, test results, known limitations, changed files and exact next command. Never claim success without executing tests.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
