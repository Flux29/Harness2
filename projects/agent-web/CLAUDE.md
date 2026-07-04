# agent-web

Scoped project instructions. Refactor governance lives in the root
`docs/HarnessRefactor.md`; read the current phase before any task.

## Commands (run from this directory)
- Tests: `uv run pytest -q` (offline suite; TestModel only, no network/tokens)
- Lint: `uvx ruff check .`
- Types: `uvx pyright src`

## Standing rules (never violate)
1. `vendor/pydantic-deepagents` is READ-ONLY. Changes go through a patch file +
   `VENDOR.txt` entry, never direct edits. First-party code reaches the harness
   only through `pydantic_deep`'s public `__init__` surface — never
   `pydantic_deep.toolsets.forking` (the deprecated shim).
2. Any behavior change updates `parity/manifest.yml` in the SAME commit, with a
   named, passing test.
3. Every PR declares a Gate 1 tier per touched file:
   byte-identical | AST-identical | behavioral (manifest entry required).
4. All live inference is `openrouter:z-ai/glm-5.2`. `TestModel` is the only
   non-5.2 path, and only in offline tests.
