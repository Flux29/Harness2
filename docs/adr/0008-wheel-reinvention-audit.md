# ADR-0008 — Wheel-reinvention audit; keep the graph, relocate backoff

**Status:** Accepted · 2026-06-30 · Resolves the "rethink pydantic-graph" question (and the orchestration trade-off raised after ADR-0006)

## Context
After the plumbing was verified end-to-end (planner, generators, memory, graph),
we audited every custom component against what `pydantic-deepagents` and its
ecosystem (`subagents-pydantic-ai`, `summarization-pydantic-ai`,
`pydantic-ai-shields`/genai-prices, `pydantic-ai-todo`, `pydantic-ai-backend`)
and `pydantic-ai` already provide, to avoid maintaining code the stack ships.

## Findings (component → verdict)
- **`graph.py` (orchestration) — KEEP.** The harness's subagents/Plan-mode/teams
  are **LLM-driven** delegation (the model chooses the path at runtime). Our flow
  needs the opposite: a **deterministic, fixed topology** (plan once → frozen →
  regen loops to Generate, never re-plans), **code-owned weighted Rank** (0.5/0.2/
  0.3, `≥7.0` gate — arithmetic, not a judgment call, which preserves the
  anti-self-grading split of ADR-0005), and **typed, resumable state** with
  per-node Postgres snapshots. The harness intentionally does not provide this.
  Note: `graph.py` is built on `pydantic_graph` — a first-party pydantic-ai
  package, not bespoke framework — so the maintenance cost is low.
- **`memory_pg.py` — KEEP.** Harness memory is file-based `MEMORY.md`, per-agent,
  prompt-injected — **not** a vector store and not pluggable to Postgres. Nothing
  in the ecosystem does Ollama-embed → pgvector semantic recall. Genuinely additive.
- **Planner/Generator/Evaluator agents + `schema.py` — KEEP (already harness-native).**
  `output_type=`, `thinking=`, `include_memory=`, `cost_tracking=` are first-class;
  the schema models are our domain shapes. No reinvention.
- **`runtime.py` 429 backoff — RELOCATE (the one real reinvention).** pydantic-ai
  ships transport-level retry (`AsyncTenacityTransport` + `wait_retry_after`,
  honoring `Retry-After`) that retries under *every* call (incl. subagents +
  embeddings). Our wrapper duplicates this at the wrong layer. **`gather_limited`
  (concurrency cap) has no built-in equivalent — KEEP it.**
- **C3 Debate-Critics — THIN-WRAP.** Build the 3 critics as harness subagents/team
  invoked *from* the `Criticize` node, but keep `Rank` weighting + the regen
  decision in deterministic Python.
- **Cost-tracking warning — model-ID matching issue, not a bug.** `cost_tracking`
  uses genai-prices (static DB). Our NVIDIA-shim path labels the model
  `openai:z-ai/glm-5.1`, which isn't in the DB. genai-prices **does** know
  OpenRouter models, so routing GLM through pydantic-ai's **native OpenRouter
  provider** makes the slug `openrouter:z-ai/glm-5.1` resolvable. No runtime
  "register custom price" API exists; the **OpenRouter dashboard is the
  source of truth** for spend.

## Decision
1. **Keep `graph.py`** as the deterministic control plane; the pydantic-graph
   "rethink" is resolved as KEEP. (Optional later: evaluate `pydantic_graph.beta`
   — parallel steps/joins/decisions — to shrink fan-out/fan-in code. Same library.)
2. **Keep `memory_pg.py`, the agents, and `schema.py`** as-is.
3. **Relocate the 429 backoff** from `runtime.py` into a retrying httpx transport
   attached to the provider (covers all calls); keep `gather_limited`.
4. **C3:** critics as harness subagents invoked from `Criticize`; Rank stays code.
5. **Cost tracking:** prefer pydantic-ai's native OpenRouter provider so prices
   resolve; otherwise compute from token counts; treat the OpenRouter dashboard
   as authoritative. Don't chase a runtime price-register API (none documented).

## Consequences
- Confidence that the custom surface is minimal and justified; the graph is not
  redundant — it's the one piece the harness deliberately doesn't replace.
- Two concrete refactors **applied 2026-06-30**: (1) 429/5xx retry relocated to a
  shared `AsyncTenacityTransport` httpx client on every provider
  (`models._retrying_http_client`); `runtime.agent_run` reduced to a thin wrapper,
  `gather_limited` kept. (2) GLM routed via pydantic-ai's native `OpenRouterProvider`
  (fixes genai-prices resolution + retry-aware HTTP). `tenacity` added to deps.
- Unverified caveats (flagged, not asserted): exact `create_deep_agent` kwargs on
  the installed version; whether a newer `pydantic-ai-shields` exposes a price
  override. Re-check on upgrades.
