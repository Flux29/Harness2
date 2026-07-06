# AgenticWork — Deep-Agent Harness + AG-UI Web Frontend

An agent that plans coding tasks, forks candidate implementations, tests each
in isolation, and keeps the winner — built on a vendored
[pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents)
harness, fronted by a CopilotKit React UI speaking the
[AG-UI protocol](https://docs.ag-ui.com/introduction) to a FastAPI backend.
Traceable end-to-end with Logfire (opt-in via `LOGFIRE_TOKEN`).

**Start here:** [`PDR.md`](PDR.md) (architecture → files) and
[`docs/adr/`](docs/adr/) (16 decision records, 0001–0016).

## Layout

| Path | What |
|---|---|
| `vendor/pydantic-deepagents/` | pristine upstream (its own MIT license) + `vendor/patches/` (one patch: public `branch_outcomes()`) |
| `LICENSE` | MIT — covers first-party code; the vendored tree keeps its own MIT license |
| `projects/agent-web/` | the web service: FastAPI + `AGUIAdapter` + MCP registry + CopilotKit frontend |
| `projects/eval-optimizer/` | C5 fork-based plan-viability pipeline (headless) |
| `docs/adr/`, `docs/PLAN-agent-web-startup.md` | decisions & the startup/always-on plan |
| `HANDOFF.md` | what was verified where (sandbox vs Windows-native) |

> Parking policy (two tiers, ADR-0021): agentic deletion is disabled. Files
> genuinely **scheduled for deletion** move to a **local-only, git-ignored,
> never-pushed** `Obsolete/` directory — a clone never receives it; git history
> (a real fork, not a squash) is the durable record. Code that is **deferred
> with a named future** (e.g. the Gen-1 pipeline substrate) instead moves to a
> **committed, import-quarantined** `eval_optimizer/legacy/` — push- and
> clone-durable, kept out of the live import path and enforced by Gate 5
> (`live-path-never-imports-legacy`).

## Quickstart (Windows)

```powershell
cd projects\agent-web
uv sync                                        # harness installs FROM vendor\, never PyPI
powershell -File scripts\build-frontend.ps1    # once, and after UI changes
powershell -File scripts\Start-AgentWeb.ps1    # one server: http://localhost:8801
```

Secrets are Windows USER environment variables (see `.env.example` files);
`.env` holds only non-secret flags. Auto-start: `scripts\Register-StartupTask.ps1`.

## Security posture (ADR-0020)

An always-on, single-user, loopback-bound local service. The composed threat
model and every control live in [ADR-0020](docs/adr/0020-composed-security-posture.md);
the essentials:
- **Bind loopback only** (`127.0.0.1`, pinned in the startup scripts, ADR-0020 §1).
  Binding beyond loopback **requires** setting `AGENT_TOKEN`.
- **`POST /agent` is guarded** (ADR-0020 §2): requests must be
  `application/json`, carry a same-origin or allowlisted `Origin`, and a
  loopback `Host` — closing the cross-origin browser drive-by that CORS alone
  did not (CORS gates the response, not the side effect).
- **`AGENT_TOKEN`** (USER env, optional): when set, `/agent` also requires
  `Authorization: Bearer <token>`; mandatory for any non-loopback bind.
- **Execution surfaces are all off by default** and individually gated
  (`EXECUTE` approval-gated, `FORKING=0`, `BROWSER_AUTOMATION=0`).
- **State** (history + checkpoints) lives in a server-only `state/` tree the
  agent cannot reach; secrets never touch `.env` or CI.

## Hard-won operational notes

- Every feature is env-gated (`TEAMS`, `EXECUTE`, `TOOL_SEARCH`, …); with
  `TOOL_SEARCH=1` the model must call `search_tools` to see MCP tools — the
  `skills/external-services` skill teaches it to.
- `execute` (shell) is approval-gated through AG-UI interrupts; browser
  automation is not — leave `BROWSER_AUTOMATION=0` unless a task needs it.
  Live Run Forking runs LLM-generated code + its tests on the host, so it is
  likewise opt-in: `FORKING=0` by default (Phase 5.2); eval-optimizer's
  headless fork path additionally requires `EVALOPT_ALLOW_HOST_EXEC=1`.
- Authoritative chat history lives in a server-only `state/` tree that agent
  file tools cannot reach (Phase 5.1); upgrading v1 deployments migrate via
  the `HISTORY_DUAL_WRITE=1` parallel-run window, not a hard cutover.
- Telemetry is the impartial witness: every claim in the ADRs' resolution
  logs is backed by a Logfire trace.
