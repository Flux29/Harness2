# eval-optimizer — agent conventions

Auto-injected into every agent + subagent by the pydantic-deepagents harness.

## What this project is

The two-agent **evaluator-optimizer** core. An Optimizer generates an artifact
toward a spec; an Evaluator skeptically grades it against that spec and returns a
structured verdict. A bounded loop iterates until pass or max iterations. Once
reliable, this pair becomes the engine that generates the five general-purpose
agents.

## Hard rules

- **uv-first.** No global `pip install`. Use `uv add` / `uv run`. (Guarded by
  the AgenticWork pre-tool-use hook in harnesses that load it; the policy binds
  everywhere — ADR-0022.)
- **Secrets via USER env vars.** Never hard-code any key. Secrets are set as user
  environment variables (e.g. `setx OPENROUTER_API_KEY ...`); `.env` holds only
  non-secret flags, never keys.
- **Reasoning vs. embeddings are split.** Reasoning runs on per-role models via
  OpenRouter (default `openrouter:z-ai/glm-5.2`; override with `PLANNER_MODEL` /
  `GENERATOR_MODEL` / `CRITIC_MODEL`). Local Ollama does embeddings — never route
  embeddings to a reasoning provider.
- **The Optimizer never grades its own work.** The Evaluator never edits the
  artifact. Keep the roles separate.

## Conventions

- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Python: 3.12+ (one workspace floor, ADR-0022), `uv` managed.
- Mind your inference provider's rate limits (a free NVIDIA tier, for example, is
  ~40 req/min with no SLA): bound loop iterations and rely on the harness cost
  tracker.
