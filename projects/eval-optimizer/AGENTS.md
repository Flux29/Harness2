# eval-optimizer — agent conventions

Auto-injected into every agent + subagent by the pydantic-deepagents harness.

## What this project is

The two-agent **evaluator-optimizer** core. An Optimizer generates an artifact
toward a spec; an Evaluator skeptically grades it against that spec and returns a
structured verdict. A bounded loop iterates until pass or max iterations. Once
reliable, this pair becomes the engine that generates the five general-purpose
agents.

## Hard rules

- **uv-first.** No global `pip install`. Use `uv add` / `uv run`. (Enforced by
  the AgenticWork pre-tool-use policy.)
- **Secrets via env only.** Never hard-code `NVIDIA_API_KEY` or any key. Read
  from `.env`.
- **Reasoning vs. embeddings are split.** GLM 5.1 (NVIDIA) reasons; local Ollama
  embeds. Don't call the NVIDIA endpoint for embeddings.
- **The Optimizer never grades its own work.** The Evaluator never edits the
  artifact. Keep the roles separate.

## Conventions

- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Python: 3.11–3.13, `uv` managed.
- Keep the NVIDIA free-tier rate limit (~40 req/min, no SLA) in mind: bound loop
  iterations and rely on the harness cost tracker.
