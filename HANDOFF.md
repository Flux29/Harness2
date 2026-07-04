# HANDOFF — Windows-native verification & remaining steps

> **COMPLETE 2026-07-02.** All native steps verified with Steven interactively:
> eval-optimizer `uv sync` + tests green (one pre-existing env-leakage test fixed);
> agent-web 10/10 tests + verify_core all-OK; live OpenRouter smoke (port 8801 —
> 8000 held by Docker) returned "LIVE WIRE OK" with reasoning events; browser run
> at localhost:3000 executed a real write_todos agent loop; Logfire tracing wired
> (`observability.py`) and confirmed via Logfire MCP (trace 019f215d…: 2 model
> calls, 1 tool execution, MCP tools/list from context7+deepwiki). Docker/pgvector
> NOT required by agent-web. Remaining items below are optional follow-ons.
>
> **FINAL 2026-07-03:** startup plan enacted end-to-end (single server,
> launcher, Task Scheduler task verified live incl. 0x80070002 uv-path fix);
> secrets migrated to USER env vars, .env files sanitized (+ .env.example
> templates); tool-discovery skill + IMPROVE loop active. This document is
> now historical record; current state lives in PDR.md and the ADRs.

Written 2026-07-02. Everything below the "Already verified" line is DONE and
E2E-tested in the Cowork Linux sandbox; the "Run natively" section is what
Claude Code (or you, in PowerShell) must confirm on Windows — mostly because
the sandbox has no Python ≥3.11, no OpenRouter egress, and no browser.

## Already verified (sandbox, 2026-07-02)
- **Consolidation:** both projects resolve `pydantic-deep` ONLY from
  `vendor\pydantic-deepagents` (`[tool.uv.sources]`, editable). Vendored
  editable install builds; `vendor\verify_core.py` extended and GREEN
  (imports, forking, patch, AG-UI adapter, MCP registry + parse fixture).
- **Vendor hygiene (IMPROVEMENTS 1–8):** `patches/0001-branch-outcomes.patch`
  (round-trip verified), `VENDOR.txt`, `revendor_check.py`, RUNBOOK retargeted;
  dead `.git` + in-tree `.venv` parked in `Obsolete\vendor-pydantic-deepagents\`.
- **agent-web backend:** 10/10 pytest E2E green (SSE stream shape, 422 on bad
  input, server-side history, two-thread isolation, healthz + /debug/mcp,
  approval interrupt with tool NOT executed). Raw `curl -N` SSE over real HTTP
  green. ADR-0012 risks 1+2 resolved (see ADR resolution log).
- **Frontend:** manual OSS-only scaffold; `npm install` + production build
  (tsc + vite) pass; `@ag-ui/client` `HttpAgent` → backend INTEROP OK
  (`frontend` sources + `package-lock.json` committed; `node_modules`/`dist`
  intentionally NOT in the workspace).

## Run natively on Windows (in order)

1. **eval-optimizer full sync (needs Python ≥3.11 — sandbox had 3.10):**
   ```powershell
   cd C:\Users\pollm\AgenticWork\projects\eval-optimizer
   uv sync            # now installs pydantic-deep from vendor\ (editable)
   uv run python ..\..\vendor\verify_core.py     # expect CORE OK + AG-UI/MCP OKs
   uv run pytest -q                              # existing smoke tests
   ```
2. **agent-web env + tests:**
   ```powershell
   cd C:\Users\pollm\AgenticWork\projects\agent-web
   uv venv; uv sync
   uv run pytest -q                              # expect 10 passed
   uv run python ..\..\vendor\verify_core.py
   ```
3. **Live OpenRouter smoke (sandbox egress was blocked):**
   ```powershell
   # key already in projects\eval-optimizer\.env — copy OPENROUTER_API_KEY into agent-web\.env
   uv run uvicorn agent_web.main:app --port 8000
   # second terminal:
   curl.exe -N -X POST http://127.0.0.1:8000/agent -H "content-type: application/json" ^
     -d "{\"threadId\":\"live-1\",\"runId\":\"r1\",\"messages\":[{\"id\":\"m1\",\"role\":\"user\",\"content\":\"Reply with exactly: LIVE WIRE OK\"}],\"tools\":[],\"context\":[],\"state\":{},\"forwardedProps\":{}}"
   # expect TEXT_MESSAGE_CONTENT deltas spelling LIVE WIRE OK, then RUN_FINISHED
   ```
4. **Browser E2E:**
   ```powershell
   cd frontend; npm install; npm run dev    # http://localhost:3000
   ```
   Chat round-trip; watch Network tab: POST /agent + SSE events. Optional:
   `npx copilotkit@latest skills onboard` (ADR-0016 keeps EI off — decline any
   platform sign-in prompts; skills install is account-free).
5. **MCP live check (optional):** set `GITHUB_MCP_PAT`, add `github` to
   `MCP_ENABLE`, restart, `GET /debug/mcp` should show `"status":"active"`;
   ask the agent to search a repo.
6. **Housekeeping (manual, human-only by design):** review `Obsolete\` and
   delete when comfortable — agents park, never delete. If Git is used outside
   this mount, note `Obsolete/` is already in `.gitignore`.

## Known constraints to keep in mind
- The AgenticWork mount can serve stale/truncated reads to the sandbox shortly
  after writes; every doc/code file in this change-set was verified from both
  sides. If Claude Code sees a truncated file, re-open after a few seconds.
- Live-fork `test_command` runs on the host (ADR-0011 trade-off 1) — unchanged.
- ADR-0016 defines the (currently disabled) Enterprise Intelligence path.
