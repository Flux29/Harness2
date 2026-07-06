# ADR-0020 — Composed security posture for the always-on local agent service

**Status:** Proposed · 2026-07-06 · resolves plan step **6.4** (a [NEW]
posture item — no §8 catalog finding; its concrete parity-affecting change is
the discovered endpoint-auth gap `disc-agent-endpoint-csrf`) · consolidates the
threat model behind ADR-0012 (trust model), 5.1 (server-only state), 5.2
(execution gates), 5.3 (bind address); unblocks the CD decision deferred from
Phase 0.3.

## Context

The critique's structural point: every security slice was individually
approved — loopback bind, server-owned history, approval-gated execute — and
**nobody assessed the assembly**. This ADR states the threat model for the
service *as deployed* (one `create_deep_agent` behind FastAPI, bound to
`127.0.0.1:8801`, auto-started by Task Scheduler at logon, single Windows user,
secrets in USER env) and rules on each control in one place.

**Actor model for a loopback-bound, single-user local service:**

1. **Remote network attacker** — cannot reach the port. 5.3 pinned
   `--host 127.0.0.1` as a stated invariant; the LAN is not a peer.
2. **Local malware running as the user** — already has the user's env, files,
   and OpenRouter/GitHub/Logfire secrets directly. No app-level control
   meaningfully raises this bar; out of scope by necessity, stated so we
   don't pretend otherwise.
3. **Browser-based cross-origin attack — the real residual, and it was
   unclosed.** A loopback bind does *not* stop it: the browser runs locally,
   so any web page the user visits can issue requests to `127.0.0.1:8801`.
   This is the CSRF / DNS-rebinding class, and it is exactly what an assembly
   review (not a per-slice one) surfaces.

**Verified this session (not asserted):** with CORS locked to the bundled UI
origin only, a browser "simple request" — `Content-Type: text/plain`,
`Origin: https://evil.example`, no preflight — POSTed to `/agent` was **fully
processed: HTTP 200, run completed, history written.** CORS governs whether the
*browser* hands the *response* back to the calling page; it does not stop the
request from arriving and causing side effects. `text/plain` is a CORS "simple"
content-type, so no preflight is triggered and the allowlist never engages.
The endpoint reads `await request.body()` with no content-type, Origin, or Host
check and no auth. So a page the user merely visits can drive their local
agent — start runs, write history, and (where `FORKING`/`EXECUTE` are enabled)
reach host execution. The individually-sensible pieces composed into an open
state-changing endpoint.

## Decision

State the posture explicitly and close the browser vector with proportionate,
layered, low-friction controls. Nothing here weakens a Phase-5 guarantee; this
is the assembly the slices were missing.

**1. Bind address — loopback, invariant (affirm 5.3).** `127.0.0.1` only,
declared in both startup scripts and the RUNBOOK. Binding beyond loopback is a
deliberate, documented act that REQUIRES the token control (below); the default
never does.

**2. `/agent` request authenticity — NEW, the core fix. A small ASGI guard,
before the handler, enforces all three:**
   - **Content-Type must be `application/json`.** Rejecting `text/plain` /
     form types removes the simple-request bypass, so a cross-origin POST now
     *requires* a CORS preflight — which the existing allowlist actually
     answers. The real AG-UI/CopilotKit client already sends JSON (the E2E
     suite posts `application/json`), so no legitimate caller breaks.
   - **Origin, when present, must be in `cors_origins`.** Defends the
     non-preflighted path directly: a foreign `Origin` is refused at the
     handler regardless of content-type.
   - **Host must be loopback** (`127.0.0.1`/`localhost[:port]`). Defeats DNS
     rebinding (the attacker's page resolves `evil.com → 127.0.0.1`; the Host
     header stays `evil.com` and is refused).
   Failures return `403` before any run starts, history load, or model call.
   Same-origin requests from the bundled UI satisfy all three unchanged.

**3. Optional bearer token — `AGENT_TOKEN` (USER env).** Unset by default
(loopback + guard #2 is the single-user baseline). When set, `/agent` also
requires `Authorization: Bearer <token>`; **required whenever the service is
bound beyond loopback.** This is the control that makes a non-loopback bind or
a future multi-user/remote deployment defensible without redesign.

**4. CORS scope — narrowed and meaningful.** `cors_origins` keeps its
deployment default (the bundled UI origin); with guard #2 forcing preflight for
cross-origin writes, the allowlist stops being decorative and becomes the
enforced boundary. `allow_methods`/`allow_headers` narrow from `*` to what the
AG-UI client uses.

**5. Execution surfaces — inventory, each gated (affirm Phase 5).** The
composed list, so the assembly is on the record:
   - **execute (shell):** approval-gated via AG-UI interrupts; Docker backend
     advised (ADR-0012/0015). Unchanged.
   - **forking (`test_command` on host):** `FORKING=0` by default (5.2);
     eval-optimizer's headless path additionally requires
     `EVALOPT_ALLOW_HOST_EXEC=1`. **Assembly note carried forward from
     ADR-0018:** the vendor test runner inherits the *full parent
     environment* (its documented SECURITY caveat) — a branch's
     `test_command` runs with whatever secrets the process holds. Recorded as
     a known property; scrubbing the child env for `test_command` is a
     tracked hardening (ISSUE-5), not a blocker, because forking is
     default-off and acknowledgment-gated.
   - **browser (Playwright):** `BROWSER_AUTOMATION=0` by default; not
     approval-gated (documented asymmetry, README).
   All three are off in the default deployment; enabling any is a deliberate,
   documented act.

**6. Secrets & state.** Secrets in USER env vars, never `.env`/committed
(secrets-scan enforces). History + checkpoints live in one server-only `state/`
tree outside every agent-writable root (5.1, ADR-0019), gitignored; that tree
is the single PII surface — its retention (no auto-expiry today) is recorded as
a known property for a future retention decision, not changed here.

**7. Task Scheduler auto-start — implications stated.** The service runs at
every logon as the logged-in user, self-restarting (RestartCount 3), for that
user's own session on loopback. It grants no privilege the user lacks and
exposes nothing beyond the local browser vector closed by #2. Acceptable as-is.

**8. CD decision (unblocks 0.3).** With the posture written down, thin CD is
affirmed as sufficient and auto-deploy-on-tag is **conditionally unblocked**:
CI may publish a versioned tag + `frontend/dist` artifact that the existing
Task Scheduler path pulls, and tag→pull automation is now permitted **provided
the request-authenticity guard (#2) is in the released build**. No secrets ever
enter CI (live verification stays local, per the existing rule); CD moves only
artifacts, never credentials.

## Consequences

- The verified cross-origin drive-by is closed: the same probe (text/plain +
  foreign Origin) returns `403`; a preflighted cross-origin write is refused by
  CORS; a rebinding Host is refused. A regression test pins each.
- No legitimate client changes: the bundled same-origin UI and the E2E suite
  (JSON, same-origin/absent Origin) pass unchanged; the token path is opt-in.
- A discovered manifest entry `disc-agent-endpoint-csrf` (source: this ADR's
  assessment) lands `changed` with named tests; Matrix C gains no new *success*
  shapes (the guard only adds `403` refusals on illegitimate requests — the
  interrupt/SSE happy paths are identical, so the Matrix C tripwire stays
  green). The posture-affirming controls (bind, execution gates, secrets) need
  no manifest movement — they were flipped by their own Phase-5 steps.
- Two known properties are recorded rather than silently accepted: the
  `test_command` env inheritance (ISSUE-5) and `state/` retention — each with a
  named home so a future decision has a starting point.
- The CD path forward is unblocked and bounded.

## Implementation sketch (lands only after this ADR is Accepted)

`settings.py`: add `agent_token: str | None` (USER env `AGENT_TOKEN`).
`app.py`: a small `@app.middleware("http")` (or dependency) on `/agent` doing
content-type / Origin / Host / optional-bearer checks → `403` with a JSON
reason before the handler runs; narrow CORS methods/headers. Tests
(`test_e2e_agui.py` / a new `test_security_posture.py`): the verified
drive-by now `403`s; same-origin JSON still `200`s; bad/absent token behavior
with `AGENT_TOKEN` set; Host-rebinding `403`. `docs/ISSUES.md`: ISSUE-5
(`test_command` env scrub) + a state-retention note. README/PDR/RUNBOOK: a
"Security posture" section pointing here; document `AGENT_TOKEN` and the
bind-beyond-loopback requirement. Manifest `crit-composed-posture` → `changed`
same-commit.
