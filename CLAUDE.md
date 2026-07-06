# Harness2

ALL refactor work is governed by docs/HarnessRefactor.md.
Read the current phase's section before starting any task.
**Current phase: 6 — exit gate 6 live session PASSED 2026-07-06** (final
merges pending; once they land the parity harness is the permanent regression
net and this line retires).
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
7. Before committing any change to .github/workflows/*.yml, validate it:
   python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" <file>
   A workflow that does not parse has never run - green history is
   meaningless if the file is invalid. Fix before commit, no exceptions.
8. Agentic deletion is DISABLED (ADR-0021). Never `rm` a first-party file.
   Files scheduled for deletion move to the local-only, git-ignored,
   never-pushed `Obsolete/`; deferred-with-a-future code moves to committed,
   import-quarantined `legacy/` (Gate 5: the live path never imports it).
   This rule binds both this refactor and any agent acting on the repo. (The
   harness's own runtime file tools — LocalBackend `delete_file`, fork-overlay
   discards — are exempt: vendor-pristine + runtime hygiene, per ADR-0021.)
