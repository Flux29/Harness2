# ADR-0012 — Pivot to an AG-UI web frontend (TUI abandoned)

**Status:** Accepted · 2026-07-01 · Redirects the "next step" of the vendor RUNBOOK
(TUI launch); complements ADR-0002/0007 (keep the harness).

## Context
The vendored harness plan (`vendor/RUNBOOK.md`) ended with "launch the terminal
assistant (TUI)". We are pivoting: the interface should be a web UI, reachable from a
browser, able to render agent state (todos, forks, costs, approvals) rather than a
terminal emulation.

The decisive discovery: `create_deep_agent(...)` returns a **plain
`pydantic_ai.Agent[DeepAgentDeps, str]`** (`pydantic_deep/agent.py`), and Pydantic AI
ships a first-class AG-UI integration (`pydantic_ai.ui.ag_ui.AGUIAdapter`,
`pydantic-ai-slim[ag-ui]` extra — deps: `ag-ui-protocol` + `starlette`). AG-UI is an
open protocol (docs.ag-ui.com) for frontend↔agent streaming: events, messages, shared
state, frontend tools, interrupts — exactly the state we want to render. The adapter
docs (pydantic.dev/docs/ai/integrations/ui/ag-ui/) show the whole server is one
FastAPI route:

```python
@app.post("/agent")
async def run_agent(request: Request) -> Response:
    return await AGUIAdapter.dispatch_request(request, agent=agent, deps=make_deps(request))
```

Alternatives considered: the vendored `examples/full_app` and `apps/deepresearch`
both hand-roll a bespoke WebSocket JSON protocol (`/ws/chat`, custom `type:` frames,
custom approval frames). That is a protocol we would own, document, and debug, with a
frontend nobody else maintains. The Vercel AI adapter exists too, but AG-UI is the
protocol CopilotKit (our chosen frontend, ADR-0013) speaks natively.

## Decision
**The UI boundary is the AG-UI protocol, served PydanticAI-natively.**

- **One backend service**, `projects/agent-web/` — FastAPI (ASGI, run under uvicorn),
  installing the vendored harness (`-e vendor/pydantic-deepagents[web,mcp,yaml]`) plus
  `pydantic-ai-slim[ag-ui]`.
- **One agent, built once** at startup via `create_deep_agent(...)` (feature flags per
  ADR-0015, MCP toolsets per ADR-0014). No custom protocol code: request → 
  `AGUIAdapter.dispatch_request()` → SSE stream of AG-UI events.
- **Per-request isolation** follows the harness's own multi-tenant rule
  (`docs/advanced/multi-user.md`): the agent holds no user state; each request gets a
  fresh `DeepAgentDeps` whose `backend` is scoped to the session/user workspace.
- **Server-owned history.** Per the Pydantic AI UI trust model, the AG-UI endpoint is
  not an auth boundary and client-sent history is untrusted. We persist message
  history server-side keyed by AG-UI thread id (via the `on_complete` callback →
  `AgentRunResult`), pass it back as `message_history`, and keep the adapter default
  `manage_system_prompt='server'`.
- **Human-in-the-loop = AG-UI interrupts.** Tools needing approval use Pydantic AI
  `requires_approval=True` → `RUN_FINISHED(outcome=interrupt)` → client `resume[]`
  (requires `ag-ui-protocol >= 0.1.19`).
- **Shared state + custom events.** Harness state (todos, fork panels, cost) is
  surfaced with `StateSnapshotEvent`/`CustomEvent` via `ToolReturn.metadata` and a
  `StateHandler` deps wrapper — the AG-UI-native mechanism, no side channel.

## Consequences
- The entire "web framework" we own is ~1 route + a session store; protocol,
  encoder, streaming, and security defaults come from `pydantic-ai` upstream. The
  bespoke WebSocket protocols in `examples/full_app` / `apps/deepresearch` are
  reference material only — we adopt neither.
- **Risk — approval plumbing.** AG-UI interrupts require `DeferredToolRequests` in the
  agent's `output_type`; `create_deep_agent`'s signature pins `output_type: None` and
  has its own `interrupt_on`/`ask_user` mechanism (built for the WebSocket era). Spike
  first: (a) pass `output_type` through `**agent_kwargs`, else (b) bridge the harness
  `ask_user` callback to AG-UI `CustomEvent` + a frontend tool. Whichever lands, the
  decision (AG-UI-native interrupts preferred) stands; only the wiring varies.
- **Risk — deps construction.** `DeepAgentDeps` has required backend/caches and
  `__post_init__` logic; a per-request factory must replicate what the harness's own
  entrypoints build. Mitigate with a `make_deps(session)` factory covered by a unit
  test, and wrap deps in a `StateHandler` dataclass for AG-UI state.
- The `.venv` currently inside the vendored tree serves the TUI install; the web
  service gets its own venv in `projects/agent-web/` (see `vendor/IMPROVEMENTS.md`).
- Observability unchanged: Logfire (ADR-0009) instruments the same `Agent`; AG-UI adds
  nothing to trace wiring.

## Resolution log (2026-07-02, sandbox E2E)
- **Risk 1 RESOLVED (option a, better than hoped):** `output_type` is a
  first-class, overloaded parameter of `create_deep_agent` (not `**agent_kwargs`);
  `output_type=[str, DeferredToolRequests]` builds and, with `interrupt_on`, the
  harness auto-combines DeferredToolRequests itself (agent.py ~1227). E2E test
  proves a `requires_approval` tool emits an AG-UI interrupt and does NOT execute.
- **Risk 2 RESOLVED:** `make_deps()` factory (`agent-web/src/agent_web/deps.py`)
  — `WebDeps(DeepAgentDeps)` dataclass with `state: UiState` (StateHandler) +
  `LocalBackend` per thread + per-session checkpoint store; unit + E2E tested
  (two threads, disjoint workspaces & histories).
- **New finding:** harness defaults `web_search`/`web_fetch` register as
  pydantic-ai BUILT-IN tools — unsupported by TestModel. Exposed as `WEB_TOOLS`
  env switch; on for real providers, off for tests.
- Verified end-to-end in sandbox: 10 pytest E2E green; raw curl SSE
  (RUN_STARTED→TEXT_MESSAGE_*→RUN_FINISHED) over real HTTP; `@ag-ui/client`
  `HttpAgent` (CopilotKit's own client class) full round-trip INTEROP OK.
  Outstanding for Windows: live OpenRouter smoke (sandbox egress blocked) +
  browser session — see HANDOFF.md.

- **Shared-state/cost surfacing (2026-07-02):** the Context section promised
  `StateSnapshotEvent` mirroring of todos/cost. Resolved more simply: CopilotKit
  renders todos directly from `write_todos` tool-call args (`useRenderTool`),
  and cost/token data lives in Logfire traces (queryable via the Logfire MCP —
  including by the agent itself). A second state channel would duplicate data
  already on the wire; `WebDeps.state` (StateHandler) remains in place for
  future genuinely-shared state. Simplicity is genius.

## Validation (when implemented)
`uvicorn` serves the endpoint; AG-UI Dojo (docs.ag-ui.com/tutorials/debugging) or
`curl -N` shows a well-formed SSE event stream for a prompt; an approval-gated tool
round-trips an interrupt; two parallel sessions never share workspace files.
