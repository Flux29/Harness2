# AgenticWork — Deep-Agent Harness + AG-UI Web Frontend

An agent that plans coding tasks, forks candidate implementations, tests each
in isolation, and keeps the winner — built on a vendored
[pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents)
harness, fronted by a CopilotKit React UI speaking the
[AG-UI protocol](https://docs.ag-ui.com/introduction) to a FastAPI backend.
Everything traced end-to-end with Logfire.

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

> Parking policy: files scheduled for deletion are moved to a **local-only**
> parking directory that is git-ignored and **never pushed** — so a clone never
> receives it. Git history (this is a real fork now, not a squash) is the durable
> record of anything removed.

## Quickstart (Windows)

```powershell
cd projects\agent-web
uv sync                                        # harness installs FROM vendor\, never PyPI
powershell -File scripts\build-frontend.ps1    # once, and after UI changes
powershell -File scripts\Start-AgentWeb.ps1    # one server: http://localhost:8801
```

Secrets are Windows USER environment variables (see `.env.example` files);
`.env` holds only non-secret flags. Auto-start: `scripts\Register-StartupTask.ps1`.

## Hard-won operational notes

- Every feature is env-gated (`TEAMS`, `EXECUTE`, `TOOL_SEARCH`, …); with
  `TOOL_SEARCH=1` the model must call `search_tools` to see MCP tools — the
  `skills/external-services` skill teaches it to.
- `execute` (shell) is approval-gated through AG-UI interrupts; browser
  automation is not — leave `BROWSER_AUTOMATION=0` unless a task needs it.
- Telemetry is the impartial witness: every claim in the ADRs' resolution
  logs is backed by a Logfire trace.
