# ADR-0019 — Durable per-thread checkpoint store now; rewind UI lands with the deepresearch→CopilotKit integration

**Status:** Proposed (revised after review) · 2026-07-05 · resolves plan step
**6.3** (`crit-checkpoint-persistence` — the critique's top congruency finding;
ISSUE-1) · **refines ADR-0015** (checkpointing row: storage delivered, UI
surfacing tracked) · builds on Phase 5.1 (server-only state tree) and the
planned deepresearch→CopilotKit feature port.

## Context

ADR-0015's feature table row — *"Checkpointing: `include_checkpoints=True`,
`checkpoint_store` per session; resume/rewind control in UI; required by
forking"* — is contradicted by the code: `make_deps` builds a fresh
`InMemoryCheckpointStore()` **per request**, the frontend has no rewind
affordance, and the web layer never handles `RewindRequested`. The plan's 6.3
question: is cross-request rewind a real requirement (**Option A**: implement
durability, keep the claim) or not (**Option B**: downgrade the claim)?

A first draft of this ADR recommended Option B on the telemetry evidence
(zero checkpoint/rewind activity ever recorded). **Review corrected the
frame**: the roadmap includes rolling the functions of the vendor's
`apps/deepresearch` into the CopilotKit UI — the rewind UI hasn't been used
because it hasn't been *ported yet*, not because it isn't wanted. A thorough
vendor-tree search then established the claim's true provenance and the
port's actual requirements:

1. **The claim describes `apps/deepresearch`, verbatim.** The reference app
   wires a checkpoint store **per session** (`app.py:556`), renders **Rewind
   and Fork buttons on every assistant message** in its web UI
   (`static/app.js:1367–1389`, timeline panel at `3048–3177`), serves
   `GET /checkpoints`, `POST /checkpoints/{id}/rewind`, and
   `POST /checkpoints/{id}/fork` (`app.py:1444–1516`, the fork endpoint via
   `fork_from_checkpoint`), and catches `RewindRequested` at app level to
   restore + persist history (`app.py:921–937`). ADR-0015's table column is
   literally "UI surfacing" — the row recorded deepresearch's pattern as the
   intended surfacing, alongside other not-yet-built rows (fork panel, cost
   meter). An intent table read as a status table.
2. **"Required by forking" is soft.** The coordinator saves `fork:<id>` /
   `post-fork:<id>` anchor checkpoints when a store is present and only
   **warns** otherwise ("rewind safety net unavailable" —
   `coordinator.py:509–516`); `ForkHandle.parent_checkpoint_id` is nullable.
   Recommended, not required.
3. **The AG-UI layer is the one place deepresearch's own pattern breaks.**
   deepresearch's per-session `InMemoryCheckpointStore` works because its
   WebSocket sessions are long-lived server objects. Our AG-UI layer is
   stateless per POST — a per-request store can never back checkpoint
   listing, rewind buttons on prior messages, or `fork:<id>` anchoring across
   turns (the critique's operational point). **A store that survives across
   requests per thread is the hard prerequisite of the planned port.**
4. **Durability is cheap and has a prepared home.** The vendor's public
   `FileCheckpointStore(directory)` persists one JSON file per checkpoint;
   the store protocol is async; the capability auto-prunes past
   `max_checkpoints` (deepresearch caps at 50). Phase 5.1's `state/` tree —
   whose settings comment already anticipated "6.3's checkpoint store if ADR
   6.3 chooses durability" — is server-only, outside every agent-writable
   root, and gitignored: checkpoints carry the same message-snapshot PII
   class as history and belong inside the same trust boundary (one tree for
   6.4 to account for).

## Decision

**Option A, split honestly along the layer boundary: the durable per-thread
store lands NOW; the rewind endpoints, `RewindRequested` handling, and UI
affordances land WITH the deepresearch→CopilotKit integration — tracked, not
implied.**

1. `make_deps` wires `FileCheckpointStore(state_dir / "checkpoints" /
   thread_slug(thread_id))` per thread. Each request constructs a store
   instance over the same per-thread directory, so checkpoints — including
   fork anchors — survive across requests *and* server restarts (stronger
   than deepresearch's own in-process scope, as a stateless HTTP layer
   requires). The 4.4 per-thread run lock already serializes access.
2. What this makes true immediately: ADR-0015's "`checkpoint_store` per
   session" (now per-thread, durable); the fork machinery's `fork:<id>` /
   `post-fork:<id>` anchoring across turns; "required by forking" is
   restated as *recommended* (the vendor's own semantics).
3. What remains deferred and is recorded as the integration's checklist —
   the deepresearch parity set: checkpoint list/rewind/fork endpoints on the
   AG-UI surface, app-level `RewindRequested` handling, and the CopilotKit
   timeline/buttons. Until then an agent-invoked `rewind_to` on the web path
   still surfaces as a run error — a known, recorded limitation and the
   telemetry tripwire for prioritizing the port.
4. ADR-0015's row is annotated: *storage delivered by ADR-0019; UI surfacing
   lands with the deepresearch→CopilotKit port.* ISSUE-1 closes.

Options rejected:

- **Option B (withdraw the claim / per-run by design)** — the first draft's
  recommendation; rejected on the corrected frame: it would resolve the
  congruency finding by deleting the capability the roadmap is about to
  need, then require re-doing this decision at port time. Zero telemetry
  reflected an unshipped UI, not absent demand.
- **Full Option A now (endpoints + UI too)** — rejected as scope creep: that
  is the integration project itself, with its own design questions (AG-UI
  event shapes for checkpoint timelines, CopilotKit rendering). Building the
  storage prerequisite without the UI it serves is deliberate sequencing,
  not congruency debt — because this ADR *says so* and names where the rest
  lands.
- **Per-thread in-memory singleton** (deepresearch's literal scope) —
  rejected: restart-fragile for an always-on Task Scheduler service, and
  `FileCheckpointStore` costs the same line of code.

## Consequences

- The critique's top congruency finding resolves with the claim made TRUE at
  the storage layer and precisely scoped at the UI layer, instead of
  withdrawn — matching the roadmap it turned out to be serving.
- Matrix D gains the checkpoint files under `state/checkpoints/<slug>/`
  (exactly the plan's stated parity impact for Option A); the tree is
  already gitignored and outside every LocalBackend root — the 5.1 negative
  test's principle extends to checkpoints with a named test.
- Fork anchors persist: a `FORKING=1` session's pre/post-fork checkpoints
  survive the request that created them — `fork_from_checkpoint` becomes
  actually usable at port time.
- Growth is bounded by the capability's auto-prune (`max_checkpoints`);
  the implementation pins the effective cap in a test so unbounded-growth
  regressions fail loudly.
- `crit-checkpoint-persistence` flips to `changed` with named tests
  (cross-request persistence, thread isolation, outside-workspace).
- Cross-reference 6.4: one server-only `state/` tree now holds history +
  checkpoints; the posture ADR reviews its permissions and retention once.

## Implementation sketch (lands only after this ADR is Accepted)

`deps.py`: `make_deps(workspaces_dir, state_dir, thread_id)` wires
`FileCheckpointStore(state_dir / "checkpoints" / slug)`; `app.py` passes
`settings.state_dir`. Tests: cross-request persistence (two `make_deps`
calls, same thread, checkpoint visible in both), isolation (distinct threads,
distinct dirs), boundary (no checkpoint file under any workspace root),
prune-cap pin. ADR-0015 row annotated; ISSUE-1 closed; manifest
`crit-checkpoint-persistence` → `changed` same-commit. The integration
checklist (endpoints, `RewindRequested` handler, UI) is recorded in
ISSUES.md as a named successor item so it cannot silently evaporate.
