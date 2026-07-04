# AgenticWork Harness Critique

Date: 2026-07-01

Scope: the whole `<workspace-root>` (AgenticWork) workspace, including root docs,
catalogs, rules, infra, evals, cache/scaffolds/notebooks, and
`projects/eval-optimizer`.

This is a critique only. It intentionally does not include a repair plan,
refactor plan, or backlog.

## 1. Executive critique

AgenticWork is currently a policy-and-POC workspace, not a complete local
realization of the Vstorm `pydantic-deep` harness surface. The strongest local
implementation is the `eval-optimizer` package, especially provider wiring,
Logfire instrumentation, pgvector memory, Docker validation, and an attempted
harness-native Live Run Forking path. The wider workspace provides useful
scaffolding intent through catalogs, rules, infra, and smoke tests, but those
pieces are thin relative to the full harness feature set.

The largest consistency issue is that the workspace carries several overlapping
architectural stories at once:

- root `PDR.md` says C5 harness-native forking is the active path and "verified
  working";
- `projects/eval-optimizer/README.md` still describes the older
  two-agent evaluator-optimizer loop as the main project;
- `docs/C5_FORK_PLAN.md` still presents graph-level forking as the spine;
- `docs/C5_FAILURE_DIAGNOSIS.md` argues for tool-less content roles, while
  `docs/adr/0011-harness-native-forking.md` later says the architectural answer is
  to embrace harness file-writing and Live Run Forking;
- `schema.py`, `graph.py`, `validate.py`, and `loop.py` preserve superseded
  architecture as live code, not just historical notes.

The most serious accuracy issue is that the local documentation overstates
readiness. The upstream Vstorm surface includes TUI/headless CLI, Live Run
Forking, DeepResearch, MCP, teams, skills, memory, context management,
checkpointing, hooks, Docker sandbox execution, browser automation, cost
tracking, and structured output. Locally, many of these are only mentioned,
available through installed package defaults, or absent from workspace-level
configuration and validation.

The most serious quality issue is that the active Live Fork implementation
depends on an internal/private method, `coordinator._build_branch_outcomes()`.
That creates a hard mismatch with the workspace's stated goal of using the
harness as shipped and staying aligned with public Vstorm capabilities.

## 2. Evidence base and versions checked

Local evidence inspected:

- root `PDR.md` and `README.md`
- `catalogs/models.yml`, `catalogs/scaffolds.yml`, `catalogs/tools.yml`
- `rules/python-env-policy.md` and `rules/hooks/agentic_pre_tool_use.py`
- `infra/README.md`, `infra/docker-compose.yml`,
  `infra/docker-compose.gpu.yml`, `infra/initdb/*.sql`,
  `infra/sandbox/Dockerfile`
- `evals/agentic-smoke` project and tests
- `projects/eval-optimizer` docs, ADRs, source, tests, and project metadata
- `scaffolds/`, `notebooks/`, and `cache/`

Upstream evidence:

- Vstorm README for `pydantic-deepagents`:
  <https://raw.githubusercontent.com/vstorm-co/pydantic-deepagents/main/README.md>
- Installed local package API from
  `projects/eval-optimizer/.venv/Lib/site-packages/pydantic_deep`

Installed package version checked:

- `pydantic_deep 0.3.34`

Installed API shape checked:

- `create_deep_agent(...)` exposes toggles for `include_todo`,
  `include_filesystem`, `include_subagents`, `include_skills`,
  `include_plan`, `include_execute`, `mcp_servers`, `context_manager`,
  `include_memory`, `hooks`, `include_checkpoints`, `include_teams`,
  `include_monitoring`, `include_improve`, `include_liteparse`,
  `web_search`, `web_fetch`, `cost_tracking`, `cost_budget_usd`,
  `fallback_model`, and `forking`.
- `LiveForkCapability(...)` exposes `max_branches`, `max_depth`, `store`,
  `keep_artifacts`, `test_command`, and `test_timeout_s`.
- `BranchSpec(...)` exposes `label`, `steer`, `model`, and `budget_usd`.

Validation state:

- `rg --files -g '!**/.venv/**' -g '!**/__pycache__/**'` completed and
  confirmed the workspace inventory.
- Targeted `Get-Content` inspections completed for root docs, catalogs, rules,
  infra, evals, project docs, ADRs, and key source files.
- `uv run pytest` was run in `projects/eval-optimizer`.
- Result: 7 tests collected, 6 passed, 1 failed.
- Failure: `tests/test_smoke.py::test_settings_defaults` expects
  `s.glm_model == "z-ai/glm-5.1"`, but the loaded environment produced
  `z-ai/glm-5.2`.

## 3. Upstream capability coverage matrix

| Capability | Upstream surface | Local state | Critique |
|---|---|---|---|
| Terminal TUI | Upstream README describes `pydantic-deep`, `pydantic-deep tui`, slash commands, live fork panels, approval dialogs, themes, model switching, and streaming tool display. | No local TUI wrapper, config, documented command, CLI dependency note, theme/config state, or smoke test. | Absent as an AgenticWork capability. The package may contain CLI support, but the workspace does not expose or validate it. |
| Headless CLI | Upstream documents `pydantic-deep run`, task files, JSON output, CI/script use. | No local headless runner docs or scripts. `fork_check.py` is a Python module, not a general harness CLI integration. | Absent at workspace level. |
| Live Run Forking | Upstream exposes `forking=True`, `LiveForkCapability`, `BranchSpec`, branch budgets, test runner, branch inspection, merge/select, diffs, and fork cost. | `forking.py` uses `LiveForkCapability`, `BranchSpec`, `BranchIsolation`, `LocalBackend`, `DeepAgentDeps`, and `merge_or_select`. | Partially implemented but fragile. It reaches into `_build_branch_outcomes()`, an internal method, and lacks a passing automated test proving the claimed active path. |
| Branch budget enforcement | Upstream supports per-branch `budget_usd` and aggregate fork budgets. | `run_forked_viability()` accepts `per_branch_budget_usd` and `aggregate_budget_usd` and passes them into `BranchSpec` / `fork`. | Present in code, but not validated by local tests or a recorded successful run. |
| Branch diffs and fork cost | Upstream exposes `diff_branches` and `fork_cost`. | Not surfaced in local reports or checks. | Unused. The local report model does not capture the upstream diagnostic surface. |
| AI judge / merge modes | Upstream supports manual, auto, auto with fallback, and vote behavior. | Local code tries deterministic `pick:<id>`, then falls back to `coordinator.resolve(strategy=MergeStrategy(kind="auto"))`. | Mixed contract. Docs say deterministic test-ratio selection, but runtime has an AI auto fallback that can select outside that stated policy. |
| Copy-on-write branch isolation | Upstream describes branch overlays and winner flush. | Local code uses `BranchIsolation()` and a temp `LocalBackend`; loser cleanup is delegated to coordinator plus final `shutil.rmtree`. | Partially present. The code claims file hygiene, but no test validates branch overlay behavior, winner materialization, or loser discard. |
| Docker sandbox execution | Upstream advertises Docker sandbox with named workspaces and persisted packages. | `infra/sandbox/Dockerfile` and `validate.py` implement a legacy Docker validator, but active `forking.py` runs host-side `pytest -q` through `LocalBackend(enable_execute=True)`. | Contradictory. The workspace contains both sandboxed and host-executed validation stories. |
| Filesystem/tool execution | Upstream provides file read/write/edit, shell, glob, grep, web, browser tools. | Deep agents default to filesystem and tool surfaces; `forking.py` explicitly enables host execution. | Present but not governed by a workspace-level harness security policy. The root hook blocks global pip installs for Codex-style tool use, not necessarily pydantic-deep agent tool execution. |
| Web search/fetch | Upstream includes web search/fetch. | `ddgs` is a dependency and `web_search` defaults may be available, but no local web-search configuration, provider policy, or validation exists. | Implicit only. |
| Browser automation | Upstream advertises Playwright browser automation with CLI `--browser`. | No browser dependency/config/test or docs in AgenticWork. | Absent. |
| DeepResearch app | Upstream README describes `apps/deepresearch`, web UI, planner, parallel research subagents, Excalidraw, file browser, Tavily/Brave/Jina search, sandbox execution, and report export. | No `apps/deepresearch` clone, app scaffold, web UI, search-provider config, Excalidraw, report export, or app command. | Absent. AgenticWork is not ready to execute the DeepResearch reference app from its current local contents. |
| Plan mode | Upstream includes dedicated planner behavior and `include_plan`. | Local code uses custom planner agents and schemas. `include_plan` is not a clearly tested workspace-level feature. | Conceptually present, but implemented through custom project logic rather than validated as the upstream Plan Mode surface. |
| Subagents / swarm | Upstream supports subagents and delegation. | Local ADRs discuss critics/subagents; code uses deep agents with default subagent capability in some places, but there is no implemented critic swarm or tested team. | Mostly aspirational. |
| Teams / message bus | Upstream exposes `include_teams`. | No local code enables `include_teams=True`; no docs map team behavior to AgenticWork roles. | Absent. |
| MCP servers | Upstream supports MCP servers and import from Claude Code. | `uv.lock` includes MCP-related packages through dependencies, and ADR-0009 mentions Logfire remote MCP. No local MCP server config or harness integration is present. | Mentioned but not integrated. |
| Persistent memory | Upstream uses file-based `MEMORY.md`; local workspace adds pgvector memory. | `memory_pg.py`, Postgres/pgvector SQL, and `memory_check.py` exist. Harness `include_memory=True` is used in some agents. | Strong but divergent. Local pgvector memory is additive, but not wired into the active C5 path and not equivalent to upstream `MEMORY.md` behavior. |
| Context compression | Upstream supports context manager, summarization, eviction, warnings, and history archive. | `create_deep_agent` calls often rely on defaults or pass `context_manager=True` only in `build_optimizer`. No local validation of compression or summarization behavior. | Mostly implicit package capability, not a workspace capability. |
| Checkpoints | Upstream supports checkpoint save, rewind, and fork. | `forking.py` passes `include_checkpoints=True` and `InMemoryCheckpointStore()`. Earlier docs discuss checkpoints. | Partially present. There is no persistent checkpoint workflow or rewind/fork-from-checkpoint validation. |
| Skills | Upstream bundles skills and supports skill directories. | `projects/eval-optimizer/skills/README.md` exists, but there are no local skill implementations in the inventory. | Placeholder only. |
| Hooks/security | Upstream exposes lifecycle hooks and `default_security_hook()`. | AgenticWork has a Codex-style pre-tool-use Python hook blocking global pip installs, but pydantic-deep agents are not configured with `default_security_hook()` or local hook wiring. | Policy exists outside the harness. Harness-native hook/security coverage is absent. |
| Fallback models | Upstream exposes `fallback_model`. | `models.py` supports provider selection but no local agent builder uses `fallback_model`. | Absent as a harness feature. |
| Structured output | Upstream supports Pydantic `output_type`. | `agents.py` uses `output_type=ExecutionPlan` and `output_type=Verdict`; smoke tests cover a Pydantic AI structured output case. | Present in project code, but partly entangled with superseded planner/generator architecture. |
| Cost tracking and budgets | Upstream supports token/USD tracking and budget exceptions. | Some agents use `cost_tracking=True`; Live Forking code passes branch budgets. ADRs discuss genai-prices/OpenRouter. | Partially present. No tests assert cost tracking, budget stop behavior, or price resolution for GLM 5.2. |
| LiteParse documents | Upstream exposes `include_liteparse=True`. | No dependency/config/tests/docs for local document parsing. | Absent. |
| Observability | Upstream works with Pydantic AI instrumentation; workspace uses Logfire. | `observability.py` configures Logfire if `LOGFIRE_TOKEN` exists and instruments Pydantic AI/httpx. ADR-0009 documents Logfire remote MCP. | Partially present and coherent, but validation depends on external credentials and was not run in the current check. |

## 4. Workspace consistency findings

### C1. The root PDR overstates the active path

`PDR.md` states "Active path - C5 harness-native forking (ADR-0011, verified
working)." The current validation set does not verify that path. The test suite
does not run `fork_check.py`, does not exercise `run_forked_viability()`, and
currently has a failing test unrelated to Live Forking. The phrase "verified
working" is stronger than the available local evidence.

### C2. The project README describes an older center of gravity

`projects/eval-optimizer/README.md` frames the package as a two-agent
evaluator-optimizer loop with GLM 5.1 and Phase 1/2 commands. The PDR frames the
active architecture as harness-native fork viability with GLM 5.2 via OpenRouter.
Both cannot be the unqualified current entrypoint.

### C3. C5 documents disagree about the forking spine

`docs/C5_FORK_PLAN.md` says graph-level forking is the POC spine and harness
checkpoint forking is optional. ADR-0011 supersedes that with harness-native Live
Run Forking as C5. The older plan remains in the same docs folder without a
front-matter warning that it is obsolete.

### C4. Failure diagnosis and ADR-0011 encode opposite lessons

`docs/C5_FAILURE_DIAGNOSIS.md` concludes that content-producing roles belong as
tool-less text emitters. ADR-0011 concludes that the correct C5 architecture is
to embrace file-writing agents and validate the materialized branch workspace.
The documents preserve both interpretations without a reader-facing reconciliation.

### C5. Superseded modules remain live and named as if current

`graph.py`, `validate.py`, `loop.py`, and older schema types remain in source
next to the ADR-0011 path. `schema.py` contains both legacy `ForkReport` /
`BranchResult` and newer `HarnessForkReport` / `HarnessBranchResult`. This makes
the public package surface read like multiple active designs rather than a
single current design plus archived experiments.

### C6. Workspace catalogs are too sparse for the stated ambition

The root catalogs name preferred tools and frameworks, but they do not capture
specific harness decisions: TUI usage, Live Forking mode, DeepResearch app
requirements, MCP servers, browser automation, security hooks, model fallback
policy, or validation expectations. As a workspace governance layer, the
catalogs do not yet match the breadth of the harness they are meant to guide.

### C7. Scaffolds and notebooks are empty despite being policy-significant

Root docs instruct agents to check `AGENTIC_SCAFFOLDS` before writing new
framework, UI, agent, notebook, or tool code. The current inventory shows no
files under `scaffolds/` or `notebooks/`. The stated workflow relies on approved
assets that are not present.

## 5. Quality and maintainability findings

### Q1. The active Live Fork path depends on a private method

`forking.py` calls `coordinator._build_branch_outcomes()`. The leading
underscore marks this as an internal surface. This is a direct maintenance risk
against a fast-moving external harness and conflicts with the repeated local
claim that the project is using Vstorm's harness as shipped.

### Q2. The Live Fork path mixes public selection with private scoring

`merge_or_select("pick:<id>")` is public, but the local code obtains the branch
ranking through an internal outcome builder. That split leaves the most important
local decision, which branch won, tied to a non-public data path.

### Q3. Test coverage does not cover the architectural claim

The test suite covers `Verdict`, settings defaults, and validator behavior. It
does not cover `models.py`, OpenRouter provider resolution, Logfire setup,
memory persistence, graph orchestration, or harness-native forking. The current
tests therefore do not support most of the architectural claims in the PDR.

### Q4. Environment loading leaks into tests

`Settings.from_env()` calls module-level `load_dotenv()`, and the test
`test_settings_defaults` sets only `NVIDIA_API_KEY`. The failure shows that
`GLM_MODEL` from the real environment or `.env` overrides the expected default.
This makes "offline, no key needed" testing less isolated than the docs imply.

### Q5. Dependency intent is broader than validated behavior

`pyproject.toml` includes `pydantic-deep`, `pydantic-ai`,
`pydantic-graph`, `ddgs`, `openai`, `psycopg`, `logfire`, and `tenacity`.
Several of these support real features, but the validated surface is much
smaller. The gap between declared dependencies and exercised behavior makes the
project look more complete than its checks demonstrate.

### Q6. Host execution and sandbox execution are both first-class in docs

The validator and sandbox Dockerfile support network-disabled candidate checks.
The ADR-0011 path accepts host-side generated-code execution through
`LocalBackend(enable_execute=True)`. Both paths may be legitimate experiments,
but as documentation they create a safety ambiguity.

### Q7. Root policy hook does not cover harness agent execution

`rules/hooks/agentic_pre_tool_use.py` blocks raw global pip installs for a
Codex-style tool payload. It is not wired into `create_deep_agent(hooks=...)` and
does not represent the upstream harness security hook surface. The workspace has
a security rule, but not a harness-integrated security posture.

### Q8. Cached artifacts and bytecode are present in project inventory

The inventory includes cache artifacts and Python bytecode under project
directories when not excluded. This does not break the harness, but it weakens
the cleanliness of a workspace intended for reproducible agent scaffolding and
evaluation.

## 6. Accuracy findings against Vstorm behavior/API

### A1. Package naming is inconsistent

User-facing docs refer to Vstorm `pydantic-deepagents`; local dependency is
`pydantic-deep`; installed import/package is `pydantic_deep`. The upstream README
also uses both the GitHub/doc naming and the install command/package naming.
Local docs do not consistently distinguish repository, PyPI package, and Python
import names.

### A2. TUI and DeepResearch are upstream features, not local features

The upstream README presents the terminal assistant and DeepResearch app as major
deliverables. AgenticWork does not contain an app clone, TUI command wrapper,
CLI install extra, web UI, DeepResearch `.env.example`, Excalidraw integration,
or search-provider setup. Local docs mention wanting these, but the workspace
does not implement them.

### A3. The workspace treats harness memory and pgvector memory as adjacent, not integrated

Upstream persistent memory is `MEMORY.md`-style harness memory. AgenticWork has a
custom Postgres/pgvector memory system. The local system may be valuable, but it
is not the same feature and is not wired into the active Live Fork path. ADR-0008
is accurate that this is additive, but the PDR does not make the operational
gap prominent.

### A4. OpenRouter and GLM model claims drift across files

Root PDR references `*_MODEL=openrouter:z-ai/glm-5.2`. The project README and
several ADRs reference GLM 5.1. `config.py` defaults bare `GLM_MODEL` to
`z-ai/glm-5.1`, while the current environment produces `z-ai/glm-5.2` during
tests. The code supports both, but the documentation does not present a single
accurate default.

### A5. Cost tracking claims are not proven locally

The upstream harness advertises real-time cost tracking and hard budget limits.
Local ADRs correctly discuss genai-prices and OpenRouter model IDs, and
`forking.py` passes budgets. No current test or report verifies token accounting,
price resolution for GLM 5.2, or budget-exceeded behavior.

### A6. Checkpointing is configured only transiently

`forking.py` uses `InMemoryCheckpointStore()`. Upstream checkpointing also
supports saving, rewinding, and forking conversation state. The local
implementation does not demonstrate durable checkpoint workflows despite ADRs
discussing checkpoint-driven architecture.

### A7. Deep agent defaults may enable more behavior than role docs imply

`create_deep_agent` defaults include many active capabilities, including
filesystem, subagents, plan, memory, monitoring, web search/fetch, context
management, cost tracking, and stuck-loop detection. Local role instructions
often sound narrow, but agent builders do not always explicitly narrow the tool
surface. The earlier C5 failure diagnosis is evidence that this mismatch has
already mattered.

## 7. Completeness gaps for TUI, Live Forking, and DeepResearch readiness

### TUI readiness

Current AgenticWork does not contain a usable local TUI integration. There is no
workspace command, no model/profile config, no tool approval policy in harness
terms, no MCP import story, no browser flag story, no slash-command validation,
and no documentation connecting `AgenticWork` paths to a `pydantic-deep tui`
session.

### Live Forking readiness

Live Forking is the closest of the requested features to a local implementation.
The implementation is still incomplete as a trustworthy workspace capability:

- current tests do not execute it;
- the current report model does not capture diffs, cost summaries, or merge
  confidence;
- branch outcome extraction uses a private method;
- deterministic selection is contradicted by the auto-judge fallback;
- host execution is accepted but not surrounded by harness-native security
  hooks;
- success is documented in PDR language more strongly than validation supports.

### DeepResearch readiness

DeepResearch is absent locally. The workspace lacks the app, UI framework,
search-provider wiring, report export flow, Excalidraw/canvas surface,
workspace file browser, research subagent roster, app-specific env docs, and
run command. The presence of `ddgs`, Logfire, pgvector, and deep-agent packages
does not constitute DeepResearch readiness.

### Whole-workspace readiness

The root workspace is not yet complete as a reusable agentic harness home:

- catalogs are generic rather than capability-specific;
- scaffolds are empty;
- notebooks are empty;
- evals contain a basic smoke project, not harness evals;
- infra supports Postgres/Ollama and legacy sandboxing, not the full TUI or
  DeepResearch app surface;
- rules express Python environment policy but not complete harness runtime
  policy.

## 8. Validation state and unverified areas

Validated in this critique:

- Workspace inventory through `rg --files`, excluding `.venv` and `__pycache__`.
- Targeted content inspection of root docs, catalogs, rules, infra, evals,
  `eval-optimizer` docs/ADRs/source/tests.
- Installed API inspection using the project venv Python.
- `uv run pytest` in `projects/eval-optimizer`.

Current validation failure:

- `uv run pytest` fails 1 of 7 tests.
- Failing test: `tests/test_smoke.py::test_settings_defaults`.
- Observed mismatch: expected `z-ai/glm-5.1`, actual `z-ai/glm-5.2`.

Not validated in this critique:

- No live `fork_check.py` run.
- No OpenRouter, NVIDIA, Anthropic, or Ollama network/model call.
- No Logfire trace lookup.
- No Postgres/pgvector container startup.
- No `memory_check.py`, `graph_check.py`, `planner_check.py`,
  `generator_check.py`, or `validate_check.py` execution.
- No TUI launch.
- No DeepResearch app launch.
- No browser automation.
- No MCP server connection.
- No Docker sandbox build or candidate execution.
- No cost-budget enforcement run.

Bottom-line critique: AgenticWork contains a promising but internally conflicted
agent harness POC. It has enough pieces to study Vstorm's harness and to run
selected experiments, but it is not yet consistent, complete, or validated
against the full set of options exposed by `pydantic-deep` / `pydantic-deepagents`.
