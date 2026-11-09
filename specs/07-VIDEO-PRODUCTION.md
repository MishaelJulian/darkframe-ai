# Video assembly

> Status: planning specification. Confirm assumptions before implementation.

## Objective
Create vertical 1080x1920 H.264 MP4 from illustrated scenes, narration, optional licensed sound, captions and gentle camera motion using FFmpeg.

## Detailed requirements
Prefer pan/zoom/parallax on stills instead of local full video diffusion. Match scenes to narration timestamps. Preserve safe margins for Reels/Shorts UI. Avoid strobing, aggressive flashes and loudness spikes.

## Implementation contract
- Implement typed Python modules with clear public interfaces and JSON schemas.
- Separate configuration from code; load secrets only from environment variables.
- Provide actionable errors, logging, deterministic test fixtures and recovery behavior.
- Make all expensive or external actions opt-in; never silently call a paid service.
- Maintain documentation and explain deviations before proceeding.

## Acceptance criteria
Validate resolution, aspect ratio, duration, audio presence, captions and output codec with ffprobe. Output one MP4 and a render manifest.

## Agent checklist
- [ ] Inspect existing code and dependencies first.
- [ ] State assumptions and unresolved questions.
- [ ] Implement only the currently authorized milestone.
- [ ] Add tests and run them.
- [ ] Report observed results and next steps.
