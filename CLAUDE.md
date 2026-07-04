# Harness2

ALL refactor work is governed by docs/HarnessRefactor.md.
Read the current phase's section before starting any task.
**Current phase: 0** (bump this line at each exit gate).
Findings reference: docs/HarnessCritique.md.

## Commands
- Tests: 'uv run pytest -q' (run inside projects/agent-web or projects/eval-optimizer)
- Lint: 'uvx ruff check .' Types: 'uvx pyright src'
- All live inference: openrouter:z-ai/glm-5.2. TestModel for offline tests only.

## Standing rules (never violate)
1. vendor/pydantic-deepagents is READ-ONLY. Changes go througha patch file + VENDOR.txt entry, never direct edits.
2. Any behavior change updates parity/manifest.yml in the SAME commit, with a named test.
3. Every PR declares a Gate 1 tier per touched file:
   byte-identical | AST-identical | behavioral (manifest entry required).
4. Secrets live in USER env vars, never in .env or committed files.
5. Commit at every completed plan step (one step = one commit minimum);
   never carry more than one step's work uncommitted.
6. Exit gates require pushed, CI-green state — not just local passing tests.
