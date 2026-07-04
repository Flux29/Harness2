# ADR-0016 — CopilotKit OSS-only now; Enterprise Intelligence as a planned later step

**Status:** Accepted · 2026-07-01 · Refines ADR-0013 (CopilotKit frontend).

## Context
CopilotKit splits into an OSS core and an Enterprise Intelligence Platform
(docs.copilotkit.ai/concepts/oss-vs-enterprise). OSS covers everything ADR-0013
needs: chat components, generative UI, frontend tools, shared state, and direct
AG-UI connectivity. Enterprise Intelligence adds persistent/durable threads, hosted
conversation history, observability, and the inspector — delivered either
cloud-hosted (CopilotKit account, `INTELLIGENCE_API_KEY`) or self-hosted on
**Kubernetes**. We have Kubernetes available, but it is a whole operational layer
the current build doesn't need: thread history is already persisted server-side in
our FastAPI service (ADR-0012), and observability is Logfire (ADR-0009). The
boundary between OSS and EI is a **runtime configuration switch**, not an
architectural fork — the React components and the AG-UI endpoint are identical
either way.

## Decision
**Ship OSS-only.** The frontend is scaffolded manually (no `copilotkit create`
account flow), uses only OSS packages, and connects straight to our AG-UI endpoint.
No `INTELLIGENCE_API_URL` / `INTELLIGENCE_GATEWAY_WS_URL` / `INTELLIGENCE_API_KEY`
in the environment; no `.copilotkit/project.json`.

**Planned inclusion path for Enterprise Intelligence** (execute only when a listed
trigger fires):

1. **Triggers.** Any of: (a) we need cross-device durable threads beyond our own
   store; (b) we want the CopilotKit inspector for debugging generative UI; (c)
   multiple frontends need shared conversation history; (d) team members without
   Logfire access need agent observability.
2. **Path A — cloud-hosted (try first, ~1 hour):** create account, run
   `npx copilotkit@latest login` + `project select` (writes
   `.copilotkit/project.json`), add the three `INTELLIGENCE_*` env vars
   (`INTELLIGENCE_API_KEY` stays server-side). No agent or endpoint changes.
3. **Path B — self-hosted on our Kubernetes** (only if data residency or cost rules
   out Path A): deploy per docs.copilotkit.ai/premium/self-hosting; budget for
   operating a stateful platform (storage, upgrades, auth integration).
4. **Exit rule.** Because the switch is env-config, reverting to OSS is removing the
   env vars — our server-side history remains the source of truth throughout, so EI
   is additive, never load-bearing for correctness.

## Consequences
- Zero account/platform dependencies now; the sandboxed build and E2E tests run
  fully offline from CopilotKit's perspective.
- We accept duplicated thread storage if EI is later enabled (ours + theirs); ours
  stays authoritative (trust model, ADR-0012). This is deliberate redundancy, not
  drift, and is the price of the clean exit rule.
- The inspector and hosted observability are unavailable until a trigger fires —
  debugging generative UI relies on browser devtools + Logfire traces meanwhile.
- `npx copilotkit@latest skills onboard` (CLI skill install + agent-assisted
  onboarding) remains available and account-free per the CLI docs' skills table; it
  is documented in the frontend README rather than baked into the build.
