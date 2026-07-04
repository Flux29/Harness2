# Agentic Build — Architecture

An agent that **plans a coding task, forks candidate implementations, tests each in
isolation, and keeps the winner** — on the `pydantic-deepagents` harness, with
provider-flexible inference and Logfire tracing — fronted by an **AG-UI web
interface** (CopilotKit React over a FastAPI/Starlette ASGI backend). Decisions and
rationale live in `docs/adr/` (0001–0016; relocated 2026-07-01 from
`projects/eval-optimizer/docs/adr/`); this file maps the architecture to the real
files that implement it.

**Consolidation rule (2026-07-01):** the harness installs **only** from
`vendor/pydantic-deepagents` (editable path dependency) — never from PyPI. Our own
code stays out of `vendor/` (pristine upstream + `patches/` + meta docs only). Files
scheduled for deletion are parked in a **local-only, git-ignored, never-pushed**
directory (never agent-deleted); git history is the durable record.

## AG-UI web frontend (ADR-0012–0016) — LIVE since 2026-07-02
The vendored harness's TUI is **abandoned** as the interface. Instead, the UI
boundary is the [AG-UI protocol](https://docs.ag-ui.com/introduction), served
PydanticAI-natively and rendered by CopilotKit. Home: `projects/agent-web/`.

| Layer | Choice | ADR |
|---|---|---|
| Frontend | CopilotKit React (`npx copilotkit@latest create`, framework: Pydantic AI; skill via `npx copilotkit@latest skills onboard`) | 0013 |
| Protocol | AG-UI (`ag-ui-protocol` types + encoder) over SSE | 0012 |
| Backend | FastAPI (Starlette-based, ASGI) — one route: `AGUIAdapter.dispatch_request(request, agent=…, deps=…)` from `pydantic-ai-slim[ag-ui]` | 0012 |
| Agent | one `create_deep_agent(...)` — full feature set enabled (forking, checkpoints, skills, sandbox execute, memory, cost budget); returns a plain `pydantic_ai.Agent`, so the adapter needs no bridge code | 0015 |
| Tools | MCP servers via harness-native `pydantic_deep.mcp` registry (`mcp.json` + builtins: github, context7, deepwiki, figma; plus logfire, postgres) | 0014 |
| Sessions | per-request `DeepAgentDeps` with per-user backend; server-owned message history keyed by AG-UI thread id | 0012 |
| Approvals | AG-UI interrupts (`requires_approval=True` → resume flow) | 0012 |

Vendor install shifts from `.[cli]` to `.[web,mcp,yaml]` (+`sandbox` when execute is
enabled) plus `pydantic-ai-slim[ag-ui]`; see `vendor/RUNBOOK.md` and
`vendor/IMPROVEMENTS.md`.

**Status 2026-07-03 — fully live on Windows** (single server on :8801 serving
UI + agent; Task Scheduler auto-start with self-restart; secrets in USER env
vars; all feature flags on incl. `TOOL_SEARCH` + `IMPROVE`; MCP roster live:
github/context7/deepwiki/logfire, resilient-degrading; approval interrupts
verified in production incl. resume; `skills/external-services` encodes the
trace-verified tool-discovery discipline). Every claim trace-backed in
Logfire; ADR resolution logs carry the receipts. Publication note: git cannot
run INSIDE this folder (mount limitation, see vendor/RUNBOOK.md) — to publish,
copy the tree to a normal directory, `git init` there, and push; `.gitignore`
+ `.env.example` files are already in place.

| File | Role |
|---|---|
| `projects/agent-web/src/agent_web/main.py` | FastAPI app: `POST /agent` (AG-UI SSE), `/healthz`, `/debug/mcp` |
| `projects/agent-web/src/agent_web/agent.py` | the one `create_deep_agent(...)` call (ADR-0015 flags, `output_type=[str, DeferredToolRequests]`) |
| `projects/agent-web/src/agent_web/deps.py` | per-thread `WebDeps` factory: `LocalBackend` workspace + checkpoint store + AG-UI `state` |
| `projects/agent-web/src/agent_web/history.py` | server-owned message history per thread (trust model) |
| `projects/agent-web/src/agent_web/mcp.py` | ADR-0014 registry wiring (builtins + `mcp.json`, resilient build) |
| `projects/agent-web/tests/` | 13 E2E tests (SSE shape, isolation, history, interrupts + resume, checkpoints, MCP prefixing) |
| `projects/agent-web/frontend/` | CopilotKit v2 + `@ag-ui/client` React app (OSS-only, ADR-0016) |
| `vendor/patches/`, `vendor/VENDOR.txt`, `vendor/revendor_check.py` | vendor hygiene (IMPROVEMENTS 1–8 enacted) |

## Active path — C5 harness-native forking (ADR-0011, verified working)
`fork_check.py` → `forking.py`: a builder agent (`create_deep_agent(forking=…)`)
produces a plan, then `ForkCoordinator.fork()` spawns one branch per approach; the
harness runs each branch's `pytest` (`test_command`); the branch with the best
`test_pass_ratio` is merged, losers discarded; per-branch and aggregate `budget_usd`
cap cost.

| File | Role |
|---|---|
| `src/eval_optimizer/forking.py` | harness Live-Fork engine: plan → fork branches → per-branch pytest → merge winner |
| `src/eval_optimizer/fork_check.py` | runnable C5 entrypoint |
| `src/eval_optimizer/models.py` | `build_model()` — `openrouter:` / NVIDIA / `ollama:` / `anthropic:`; retry transport |
| `src/eval_optimizer/config.py` | env `Settings` (per-role models, keys, URLs) |
| `src/eval_optimizer/schema.py` | `HarnessForkReport`, `HarnessBranchResult` |
| `src/eval_optimizer/observability.py` | Logfire, opt-in via `LOGFIRE_TOKEN` |
| `.env` | non-secret config only (`*_MODEL`, URLs) — secrets are USER env vars; see `.env.example` |

## Infrastructure (containers)
| File | Role |
|---|---|
| `infra/docker-compose.yml` | Postgres+pgvector (`agentic`) + Ollama — host ports 5433 / 11435 |
| `infra/docker-compose.gpu.yml` | Ollama GPU overlay |
| `infra/sandbox/Dockerfile` | `evalopt-sandbox` image (ruff + pytest) |
| `infra/initdb/01_init.sql`, `infra/initdb/02_dedup.sql` | pgvector schema + content dedup |

## Durable memory (built and verified; not wired into the C5 path)
`memory_pg.py` — Ollama embeddings → Postgres/pgvector, sha256 dedup, per-agent
schemas; proven by `memory_check.py`. Available for reuse; the harness-native fork
path does not call it.

## Verification scripts (each proves one piece)
`check_connection.py` (endpoint + tool calling), `planner_check.py`,
`generator_check.py`, `memory_check.py`, `graph_check.py`, `validate_check.py`,
`tests/test_validate.py`, `tests/test_smoke.py`. Support: `runtime.py`
(`agent_run` + `gather_limited`), `agents.py` (Planner/Generator/Evaluator builders)
— used by the planner/generator checks.

## Legacy / superseded (retained on disk, not the active path)
| File | Superseded by |
|---|---|
| `graph.py`, `graph_check.py` | ADR-0011 (custom pydantic-graph forking → harness forking) |
| `validate.py`, `validate_check.py` | harness `test_command` (Docker sandbox no longer used by `forking.py`) |
| `loop.py` | the fork pipeline (2-agent evaluator-optimizer reference) |
| `schema.py`: `ExecutionPlan`, `Candidate`, `Critique`, `RankedCandidate`, `ForkReport`, `BranchResult`, `ValidationResult` | the `Harness*` models |

## Scaffolding (original AgenticWork)
`catalogs/`, `rules/`, `evals/agentic-smoke/`, `projects/eval-optimizer/AGENTS.md`,
`projects/eval-optimizer/skills/`.
