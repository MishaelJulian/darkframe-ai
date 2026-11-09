# Antigravity Agent Operating Instructions

Read `specs/00-MASTER-PLAN.md`, `specs/01-SYSTEM-ARCHITECTURE.md`, and `specs/14-IMPLEMENTATION-ROADMAP.md` first; then read the relevant module spec.

## Non-negotiable rules
1. Plan before coding. Never implement the whole system in one pass.
2. Ask permission before downloads >500 MB, package installs, destructive actions, paid APIs, credential setup or publishing.
3. Use local RTX 4050 6 GB VRAM and 24 GB RAM; no cloud fallback without explicit permission.
4. Original storytelling only: no creator transcripts, copied narration, cloned voices or derivative scripts.
5. Every central factual claim must be traceable to evidence; uncertain rights/facts block publishing.
6. Keep credentials in .env (gitignored); never print secrets.
7. Every change includes tests and a concise change log; distinguish untested from verified behavior.
8. Stop after each milestone for user review.

## First assignment
Inspect environment and installed ComfyUI Desktop; verify local API availability, installed models, Python, FFmpeg and GPU. Produce an audit report and proposed M1 implementation plan. Do not install/download anything yet.
