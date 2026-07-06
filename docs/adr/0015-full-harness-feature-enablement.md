# ADR-0015 — Full harness feature enablement (sans TUI)

**Status:** Accepted · 2026-07-01 · Builds on ADR-0011 (harness-native forking),
ADR-0012 (AG-UI surface); completes ADR-0007's "keep the harness" by actually using it.

## Context
The vendored harness (0.3.34 + `branch_outcomes()` patch) ships far more than the
forking path we use today. `create_deep_agent()` exposes every feature as a flag or
capability; most defaults are already on. The apps directory contains four
frontends/adapters: `cli` (TUI — **abandoned**, ADR-0012), `deepresearch` (bespoke
WebSocket web app — superseded by AG-UI), `acp` (Zed/editor protocol adapter), and
`harbor` (Terminal-Bench eval adapter). The question is which of the library features
to enable for the web agent, and how each shows up in the UI.

## Decision
**Enable the full library feature set behind `create_deep_agent` flags; adopt none of
the `apps/`.** One agent definition in `projects/agent-web/agent.py` is the single
source of truth.

Already-on defaults we keep (no code, listed for the record): todo/plan
(`include_todo`, `include_plan`), filesystem tools, subagents (+ builtin subagents),
skills, memory (`include_memory`), monitoring, context manager + eviction
(`eviction_token_limit=20_000`), history archive, stuck-loop detection, cost tracking,
`web_search`/`web_fetch`, thinking (`"high"`), `patch_tool_calls`, retries.

Deliberate opt-ins:

| Feature | Switch | UI surfacing (per ADR-0012/0013) |
|---|---|---|
| Live forking | `forking=LiveForkCapability(test_command="pytest -q", budgets…)` | fork panel via `CustomEvent`s; deterministic pick via patched `branch_outcomes()` (ADR-0011) |
| Checkpointing | `include_checkpoints=True`, `checkpoint_store` per session | resume/rewind control in UI; required by forking *(2026-07-06, ADR-0019: durable per-thread storage delivered in the state tree; the rewind UI/endpoints land with the deepresearch→CopilotKit port — ISSUE-4; "required by forking" is the vendor's warn-if-missing recommendation, not a hard dependency)* |
| Sandbox execution | extra `.[sandbox]` + Docker backend for `include_execute` | approval-gated execute (interrupts) |
| Skills dirs | `skill_directories=[projects/eval-optimizer/skills, …]` + `.[yaml]` | skill invocations render as tool cards |
| Browser automation | extra `.[browser]` (Playwright) | opt-in flag per session; off by default |
| Tool search | `tool_search=True` **once MCP roster grows** (ADR-0014) | transparent |
| Teams | `include_teams=True` — deferred until a concrete multi-agent need | — |
| Improve / liteparse / message queue / periodic reminder | off until needed | — |
| Cost budget | `cost_budget_usd` + `on_cost_update` | live cost meter via `CustomEvent` |
| Output styles | `output_style` | server-side config |

Explicitly out of scope: `apps/cli` (TUI), `apps/acp` (editor integration — nothing
against it, just not this build), `apps/harbor` (benchmark adapter; revisit if we
want Terminal-Bench scores). `apps/deepresearch` is mined for ideas (planner +
parallel research subagents pattern) but its web layer is dead weight for us.

Durable memory note: harness `include_memory` is file-backend memory. The pgvector
memory (`memory_pg.py`, ADR-0004) stays available; the postgres MCP server
(ADR-0014) is the simplest bridge if the agent needs vector recall. No new memory
code.

## Status update (2026-07-02)
The "deliberate opt-ins" above are now **env-gated in `projects/agent-web`**
(`TEAMS`, `LITEPARSE`, `EXECUTE`, `BROWSER`, `TOOL_SEARCH` — all off by default;
heavy deps behind `uv sync --extra full`). Build-verified: the agent constructs
with each flag on. `EXECUTE=1` wires `interrupt_on={"execute": True}`, so shell
commands pause into AG-UI approval interrupts. `fallback_model` added via
`FALLBACK_MODEL`. Enabling a feature is a config change, not a code change —
the ledger's "off until needed" stance is unchanged, only the switch moved
within reach.

**2026-07-03:** Steven flipped every switch on (incl. `TOOL_SEARCH`, `IMPROVE`
— the latter added as an env flag after the GitHub-task episode showed model
mistakes are best mitigated by harness infrastructure: skills + instructions +
the /improve session-analysis loop). First custom skill lives at
`projects/agent-web/skills/external-services/SKILL.md`, encoding trace-verified
tool-discovery discipline and GitHub API pitfalls. `BROWSER_AUTOMATION` remains
the one flag recommended OFF by default: browser tools are not approval-gated
and were twice observed attempting human-style logins.

## Consequences
- Feature enablement is configuration, not construction — the whole decision
  compiles down to one well-commented `create_deep_agent(...)` call plus two extras
  in the install line (`[web,mcp,yaml,sandbox]`).
- Per-session state (checkpoints, memory, plans, history archive at
  `.pydantic-deep/messages.json`) all flows through `ctx.deps.backend` — the
  per-request backend isolation of ADR-0012 automatically isolates every feature.
  No feature may bypass the backend.
- Each opt-in adds tools to the prompt; the mitigation ladder is: leave off until
  needed → `tool_search=True` → then argue. Off-by-default rows above are the
  ledger of what we consciously deferred, so nothing is rediscovered by accident.
- Forking + checkpointing on the web host carries ADR-0011's trade-off 1 (branch
  `test_command` executes on the host). The sandbox extra covers `execute`, not
  branch tests; Docker-verifying only the fork winner remains the accepted stance.
- The `eval-optimizer` C5 pipeline keeps its own headless entrypoint
  (`fork_check.py`); the web agent is a second consumer of the same vendored
  harness, not a replacement. Both must keep working after any re-vendor
  (`vendor/verify_core.py` + web smoke test).

## Validation (when implemented)
One integration test boots the agent with the full flag set and asserts: tool list
contains todo/fs/subagent/skill/fork tools; a fork of two trivial branches selects
by `branch_outcomes()`; checkpoint create/restore round-trips; cost events fire; TUI
extras (`textual`) are absent from the web venv.
