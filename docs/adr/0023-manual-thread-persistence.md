# ADR-0023 — Manual thread persistence over Enterprise Intelligence; runs survive their clients

**Status:** Accepted · 2026-07-06 · resolves the session-management half of
**ISSUE-4** (`feat-thread-persistence`, `feat-run-survival`) · refines
ADR-0016 (its trigger (a) — durable threads — fired in live testing; the
manual path was chosen over enabling the platform) and ADR-0020 (guard
variance below).

## Context

First live sessions exposed the gap ADR-0016 deferred: reloads lost the
session (and killed in-flight runs via SSE disconnect), no thread list, no
transcript rehydration, and a pending approval wedged its thread. CopilotKit
Enterprise Intelligence closes all of this natively but adds an
account/platform dependency, and its `useThreads`/`CopilotThreadsDrawer` are
license-gated. The manual path uses CopilotKit's documented escape hatches —
the provider-controlled `threadId` prop arms CopilotChat's per-thread
`connect()` lifecycle, which plain `HttpAgent` leaves unimplemented — plus
storage we already own (the 5.1 server-authoritative history tree).

## Decision

**Own the storage; ride the native seams. No platform account.**

1. **Store:** a derived JSON index (`state/threads-index.json`, upserted by
   `history.save`) records the ORIGINAL thread id + list metadata; when
   missing it regenerates from disk, sweeping legacy
   `workspaces/<slug>/history.json` — the pre-5.1 dormant-thread backfill.
   Postgres/pgvector (ADR-0004 infra) was evaluated and deliberately
   reserved for future conversation *search*; as a plain metadata index it
   adds a dependency + DB-down fallback logic and still needs the same
   backfill. The vendor memory feature is agent-facing prose — not a thread
   store.
2. **API:** additive `GET /threads` and `GET /threads/{id}/messages`
   (transcript via the native `AGUIAdapter.dump_messages`, pending approvals
   derived from trailing unreturned tool calls, id-parity pinned against a
   live paused run). **Guard variance (ADR-0020):** the content-type rule is
   waived for these body-less GETs — it exists to force preflight on
   cross-origin *writes*; bearer/Origin/loopback-Host all still apply.
3. **Runs survive their clients:** POST /agent executes the run in a
   background task teeing events to the response; disconnect cancels only
   the tee, so `on_complete` (the history save) always fires. `running`
   surfaces per thread; live mid-stream reattach is deferred.
4. **Frontend:** `PersistentAgent.connect()` replays transcript + pending
   interrupts through the framework's own event pipeline (ApprovalBanner
   unchanged); a hand-rolled sidebar (drawer list is license-gated) drives
   the provider-controlled `threadId`.

## Consequences

- Reload/switch/reopen all rehydrate; interrupted threads re-offer
  Approve/Deny instead of wedging; no work is lost to a disconnect again.
- Zero new services or accounts; client transcripts stay display-only — the
  model is fed only `history.load` output (ADR-0012 trust model unchanged).
- ADR-0016's EI path remains open (cross-device sync, multi-tenancy would
  re-fire it); this ADR removes its trigger (a).
- Deferred, recorded in ISSUE-4: live mid-stream reattach; checkpoint
  surfacing; pgvector conversation search.
