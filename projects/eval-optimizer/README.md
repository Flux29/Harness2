# eval-optimizer

The two-agent **evaluator-optimizer** core (PDR Phase 1–2). An Optimizer generates
an artifact toward a spec; an Evaluator skeptically grades it and returns a
structured `Verdict`; a bounded loop iterates until pass or `max_iterations`.

- **Reasoning:** per-role models via OpenRouter (default `openrouter:z-ai/glm-5.2`);
  NVIDIA and local Ollama are also supported providers (ADR-0003).
- **Harness:** `pydantic-deepagents` (PyPI `pydantic-deep`).
- **Embeddings (Phase 3):** local Ollama, 1024-dim, pinned.

## Setup (Windows, uv)

```powershell
cd <workspace-root>\projects\eval-optimizer
copy .env.example .env       # non-secret config only; set keys (e.g. OPENROUTER_API_KEY) as USER env vars
uv sync                      # creates .venv from pyproject.toml
```

## Phase 0 — prove the endpoint works

```powershell
uv run python -m eval_optimizer.check_connection
```

Exit criterion: prints a chat reply **and** a successful `add(...)` tool call.
If tool calling doesn't fire, switch `GLM_MODEL` in `.env` to a fallback agentic
model (e.g. a Llama/Nemotron variant on build.nvidia.com) and re-run.

## Phase 1/2 — run the loop (deferred, ADR-0021)

```powershell
uv run python -m eval_optimizer.legacy.loop
```

Runs a throwaway palindrome-function task end-to-end through Optimizer ->
Evaluator -> feedback -> repeat, and prints whether it passed. The Gen-1
Planner→Generators→Critics strata (`loop`, `graph`, `validate`, `agents`, and
the `*_check` entrypoints) are **deferred, not deleted** — relocated to the
committed, import-quarantined `eval_optimizer/legacy/` package (ADR-0021). The
live path is harness-native forking (`fork_check` → `forking`).

## Offline tests (no key needed)

```powershell
uv run pytest
```

## Layout

```
src/eval_optimizer/
  config.py            # env-driven Settings
  models.py            # provider-flexible model wiring (OpenRouter / NVIDIA / Ollama)
  agents.py            # Verdict + build_optimizer() + build_evaluator()
  loop.py              # bounded evaluator-optimizer driver (+ __main__ demo)
  check_connection.py  # Phase 0 endpoint + tool-calling check
tests/test_smoke.py    # offline tests
```

## Notes / TODO

- `agents.py` uses the documented `create_deep_agent` kwargs. Verify against the
  installed version:
  `uv run python -c "import pydantic_deep, inspect; print(inspect.signature(pydantic_deep.create_deep_agent))"`
- Phase 3 adds `memory_pg.py` (Ollama embeddings -> Postgres `agentic` DB) and the
  `docker compose -p agentic up -d` stack under `../../infra`.
