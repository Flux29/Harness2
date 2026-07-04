# PLAN — agent-web startup, always-on, and freshness

Goal (from Steven's todo): open `localhost` in a browser and the agent just
works — no terminals, auto-started, self-healing, frontend always current.
Written 2026-07-02. Phases are ordered; each is independently shippable.

> **ENACTED 2026-07-02** — Phase 0 done (secrets stripped from both .env files;
> env vars authoritative; NVIDIA_API_KEY still pending setx). Phase 1 done
> (static mount in app.py, same-origin /agent, vite dev proxy, healthz reports
> harness version + frontend build time; 13/13 tests green). Phase 2+3 scripts
> written: `scripts/Start-AgentWeb.ps1`, `Create-DesktopShortcut.ps1`,
> `build-frontend.ps1`, `Register-StartupTask.ps1`. Windows-side remainder:
> run build-frontend once, optionally register the task + shortcut. Frontend
> build verification delegated to the Windows build (sandbox resource-starved;
> changes since last green build were config-only).
>
> **2026-07-03:** Phase 3 verified live — task fired at logon-equivalent,
> served UI + agent, self-registered after the 0x80070002 (bare `uv`) fix;
> registrar now bakes in the absolute uv.exe path. Known cosmetic: the task
> opens a visible console window; polish option is wrapping the action in
> `powershell -WindowStyle Hidden -Command ...` if it grates.

## Phase 0 — secrets to real environment variables (prereq, agreed earlier)
`setx` each secret (GITHUB_MCP_PAT, OPENROUTER_API_KEY, LOGFIRE_TOKEN,
LOGFIRE_READ_TOKEN) as *user* environment variables; strip them from `.env`,
keeping only non-secret flags there. python-dotenv never overrides real env,
so this needs zero code changes — and a lost `.env` line can no longer
disable a credential (the MCP_ENABLE regression class disappears for secrets).
Task Scheduler processes see user env vars; they do NOT reliably see
terminal-session vars — this phase is what makes Phase 3 work.

## Phase 1 — ONE server, not two (the architectural fix; ~15 lines)
FastAPI serves the **built** frontend as static files:
- `npm run build` produces `frontend/dist/` (already verified working).
- `app.py` mounts it: `app.mount("/", StaticFiles(directory=..., html=True))`
  registered AFTER the /agent, /healthz, /debug routes.
- Frontend `.env` for the build sets `VITE_AGENT_URL=/agent` (same-origin —
  CORS ceases to exist as a concern).
Result: `http://localhost:8801` IS the app. Node/Vite become build-time-only
tools; the two-terminal problem is deleted rather than managed. Vite dev mode
(`npm run dev` on :3000) remains available when actively editing UI.

## Phase 2 — one-click launcher with icon
`scripts\Start-AgentWeb.ps1`: if `GET /healthz` fails, start uvicorn
(hidden window, correct workdir), wait for healthz, then `Start-Process
http://localhost:8801`. Desktop shortcut (.lnk) targeting
`powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File <script>`
with a custom `.ico` (any bitmap converts; shortcut icons must be .ico).
Double-click → browser opens on a live agent, whether or not the server was
already up. (A compiled .exe adds nothing over the .lnk except AV headaches.)

## Phase 3 — always-on via Task Scheduler
Task "agent-web" → trigger: **At log on** → action: `uv run uvicorn
agent_web.main:app --port 8801` with Start-in = the agent-web dir →
Settings: "If the task fails, restart every 1 minute, up to 3 times".
Optional hardening: a second task every 5 min runs a 3-line watchdog
(curl /healthz; on failure `schtasks /End` + `/Run` the main task).
Not a Windows Service on purpose: Task Scheduler is built-in, debuggable,
and sufficient; services (NSSM/WinSW) are the escalation path if ever needed.

## Phase 4 — freshness
- **Backend / harness (Deep Agents vendor):** the editable install means any
  re-vendor is live on next process restart — add "restart the agent-web
  task" as the final step of the RUNBOOK re-vendor procedure. No pipeline.
- **Frontend:** static mode serves whatever `dist/` holds. After UI edits:
  `npm run build` (wrap as `scripts\build-frontend.ps1`). Optional: nightly
  Task Scheduler rebuild at 04:00 for set-and-forget freshness.
- **Version visibility:** `/healthz` extended to report harness version +
  frontend build timestamp, so "am I stale?" is a URL, not an investigation.

## Explicitly rejected (simplicity is genius)
Docker-compose for the app itself (adds a VM layer to reach localhost),
electron wrapper (a browser to open a browser), auto-git-pull of vendor
(re-vendoring is deliberate per RUNBOOK, never automatic).
