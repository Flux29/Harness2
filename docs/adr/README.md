# Architecture Decision Records

Short, dated records of the significant decisions behind the agentic build.
Format: Status · Context · Decision · Consequences. Newer ADRs may supersede
older ones (noted inline).

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-windows-native-workspace.md) | Windows-native workspace; DevDrive/Hyper-V VM deferred | Accepted |
| [0002](0002-pydantic-deepagents-harness.md) | pydantic-deepagents as the agent harness | Accepted |
| [0003](0003-provider-flexible-inference.md) | Provider-flexible, per-role inference + rate-limit resilience | Accepted |
| [0004](0004-durable-memory-pgvector.md) | Durable memory on Postgres + pgvector; local model-locked embeddings | Accepted |
| [0005](0005-planner-generators-critics.md) | Planner → Tree-of-Generators → Debate-Critics architecture | Accepted |
| [0006](0006-pydantic-graph-orchestration.md) | pydantic-graph 2.x as the orchestration substrate | Accepted |
| [0007](0007-keep-deep-agent-harness.md) | Keep the deep-agent harness (bare-Agent refactor rejected) | Accepted |
| [0008](0008-wheel-reinvention-audit.md) | Wheel-reinvention audit; keep the graph, relocate backoff | Accepted |
| [0009](0009-observability-logfire.md) | Observability: Logfire (cloud) + remote MCP for diagnostics | Accepted |
| [0010](0010-fork-based-plan-viability.md) | Fork-based plan-viability (Live Forking) as C5 | **Superseded by 0011** |
| [0011](0011-harness-native-forking.md) | Adopt harness-native Live Run Forking for C5 | Accepted |
| [0012](0012-ag-ui-web-frontend-pivot.md) | Pivot to an AG-UI web frontend (TUI abandoned) | Accepted |
| [0013](0013-copilotkit-react-frontend.md) | CopilotKit React frontend over the AG-UI endpoint | Accepted |
| [0014](0014-mcp-server-wiring.md) | MCP server wiring via the harness-native registry | Accepted |
| [0015](0015-full-harness-feature-enablement.md) | Full harness feature enablement (sans TUI) | Accepted |
| [0016](0016-copilotkit-oss-only-enterprise-later.md) | CopilotKit OSS-only now; Enterprise Intelligence later | Accepted |

Parent document: `../../PDR.md` (Agentic Build PDR v1.1). Relocated 2026-07-01 from
`projects/eval-optimizer/docs/adr/` (workspace-level decisions belong at workspace
level; vendor/ stays pristine).
