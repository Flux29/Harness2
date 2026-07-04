# eval-optimizer

The two-agent **evaluator-optimizer** core (PDR Phase 1–2). An Optimizer generates
an artifact toward a spec; an Evaluator skeptically grades it and returns a
structured `Verdict`; a bounded loop iterates until pass or `max_iterations`.

- **Reasoning:** NVIDIA-hosted GLM 5.1 (`z-ai/glm-5.1`, OpenAI-compatible).
- **Harness:** `pydantic-deepagents` (PyPI `pydantic-deep`).
- **Embeddings (Phase 3):** local Ollama, 1024-dim, pinned.

## Setup (Windows, uv)

```powershell
cd C:\Users\pollm\AgenticWork\projects\eval-optimizer
copy .env.example .env       # then edit .env: paste your NVIDIA_API_KEY
uv sync                      # creates .venv from pyproject.toml
```

## Phase 0 — prove the endpoint works

```powershell
uv run python -m eval_optimizer.check_connection
```

Exit criterion: prints a chat reply **and** a successful `add(...)` tool call.
If tool calling doesn't fire, switch `GLM_MODEL` in `.env` to a fallback agentic
model (e.g. a Llama/Nemotron variant on build.nvidia.com) and re-run.

## Phase 1/2 — run the loop

```powershell
uv run python -m eval_optimizer.loop
```

Runs a throwaway palindrome-function task end-to-end through Optimizer ->
Evaluator -> feedback -> repeat, and prints whether it passed.

## Offline tests (no key needed)

```powershell
uv run pytest
```

## Layout

```
src/eval_optimizer/
  config.py            # env-driven Settings
  models.py            # GLM 5.1 wiring (pydantic-ai OpenAI-compatible)
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
