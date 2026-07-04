# ADR-0013 — CopilotKit React frontend over the AG-UI endpoint

**Status:** Accepted · 2026-07-01 · Depends on ADR-0012 (AG-UI backend). Refined by ADR-0016: OSS-only, no Enterprise Intelligence account/platform for now.

## Context
ADR-0012 gives us a standards-compliant AG-UI SSE endpoint. We need a frontend that
speaks AG-UI without us writing a protocol client. CopilotKit
(github.com/copilotkit/copilotkit) is the reference AG-UI frontend stack — AG-UI was
introduced by the CopilotKit team — and ships a documented PydanticAI integration
(docs.copilotkit.ai/pydantic-ai): prebuilt chat components
(`CopilotChat`/`CopilotSidebar`/`CopilotPopup` from `@copilotkit/react-core/v2`),
generative UI (tool rendering, state rendering), frontend tools, shared state, and
threads. This is the **one sanctioned exception** to "PydanticAI-native everywhere":
the browser side is React/TypeScript because that is where the maintained AG-UI
client ecosystem lives.

Options for the frontend↔backend link: (a) point CopilotKit directly at our AG-UI
endpoint via `@ag-ui/client` (HttpAgent), or (b) interpose CopilotKit's Copilot
Runtime (a Node middleware adding model routing, persistence hooks, enterprise
platform features). We have exactly one agent and one endpoint.

## Decision
**CopilotKit React app, connected directly to the AG-UI endpoint. No Copilot Runtime
middle layer.**

- Scaffold with the CopilotKit CLI: `npx copilotkit@latest create` (framework prompt:
  **Pydantic AI**), then `npx copilotkit@latest skills onboard` — per the CLI docs it
  installs CopilotKit agent skills for supported coding agents and starts
  agent-assisted onboarding, so our coding agents integrate CopilotKit correctly.
  Frontend lives at `projects/agent-web/frontend/`.
- Backend URL points at the FastAPI AG-UI route from ADR-0012 (agent on :8000, UI on
  :3000, per the CopilotKit quickstart layout).
- Start with prebuilt `CopilotChat`; add generative UI incrementally:
  tool-rendering for high-signal harness tools (`write_todos`, fork/merge, subagent
  spawn), state-rendering bound to the `StateSnapshotEvent`s ADR-0012 emits (todos,
  cost, fork panel), and the interrupt/approval UI for `requires_approval` tools.
- Frontend tools (browser-side actions the agent can call) are allowed but start
  empty — add only when a concrete need appears.

## Consequences
- We own zero protocol code on either side of the wire; UI work is React components
  against typed AG-UI events.
- A Node 20+ toolchain enters the repo (frontend only). CI/dev docs must cover two
  runtimes; the Python side remains installable and testable without Node.
- Skipping Copilot Runtime forfeits its thread persistence and enterprise
  observability — acceptable: history persistence is already server-side in FastAPI
  (ADR-0012) and observability is Logfire (ADR-0009). If multi-agent routing or
  CopilotKit Cloud features are wanted later, the Runtime can be added between UI and
  endpoint without changing the agent (it consumes AG-UI too) — a reversible decision.
- CopilotKit's default starters assume OpenAI; ours is provider-flexible
  (ADR-0003, OpenRouter et al.) — model choice stays entirely server-side in
  `create_deep_agent(model=...)`, invisible to the frontend.

## Validation (when implemented)
`npm run dev` + `uvicorn`: chat round-trips; a `write_todos` call renders a custom
component instead of raw JSON; an approval interrupt renders accept/deny and resumes;
thread switch reloads server-persisted history.
