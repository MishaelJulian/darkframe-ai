# Original storytelling engine

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Develop original conversational suspenseful narration using general techniques: immediate curiosity, progressive disclosure, meaningful turn and satisfying payoff.

## Detailed requirements
Do not imitate MrBallen’s exact wording, signature phrases, voice or distinctive narrative arrangement. Story architect plans series arc before episodes. Target ~120–150 spoken words per 60-second episode, then adjust to actual TTS duration. Avoid manufactured cliffhangers, invented thoughts/dialogue and false certainty. Attach fact IDs to factual sentences.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Produce validated episode_plan.json, script.json and visual storyboard. Use independent critic and fact-grounding gate; retries capped at two.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
