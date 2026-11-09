# Project charter

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Build an original, evidence-grounded short-form mystery storytelling pipeline producing dark 2D 9:16 episodes of approximately 60 seconds. Prioritize local processing, commercial rights, low cost, and staged automation.

## Detailed requirements
The channel covers independently researched real mysteries and unusual true stories. Never repackage creator scripts or video. Start with one approved episode, then a four-episode series, then scheduling. Existing ChatGPT Plus and Google AI Pro/Antigravity access do not imply unlimited API credits.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Define scope, non-goals, acceptance metrics, review gates and assumptions. Target zero additional subscription/API expenditure for a 14-day local trial; electricity, connectivity and existing subscriptions are excluded.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
