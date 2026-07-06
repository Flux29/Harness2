# ADR-0019 — Checkpoints are per-run; the durable cross-request rewind claim is withdrawn

**Status:** Proposed · 2026-07-05 · resolves plan step **6.3**
(`crit-checkpoint-persistence` — the critique's top congruency finding; tracked
as ISSUE-1) · **corrects ADR-0015** (checkpointing row) · informed by Phase 5.1
(server-only state tree) and live telemetry.

## Context

ADR-0015's feature table claims: *"Checkpointing — `include_checkpoints=True`,
`checkpoint_store` per session; resume/rewind control in UI; required by
forking."* The critique found the code disagrees, and the plan (2.6/6.3)
deliberately HELD the docs edit until this decision: is cross-request rewind a
real requirement (**Option A**: implement durability and keep the claim) or
not (**Option B**: downgrade the claim to per-run and keep
`InMemoryCheckpointStore`)?

What the refactor and the impartial witness established:

1. **The claim is false three times over, not once.**
   - *Scope:* `make_deps` builds a fresh `InMemoryCheckpointStore()` **per
     request** — not even per-session. Nothing survives a POST.
   - *UI:* the frontend contains **zero** checkpoint or rewind references.
     There is no "resume/rewind control in UI" to be backed by any store.
   - *Rewind path:* the vendor's `rewind_to` tool raises `RewindRequested`,
     which is designed to propagate out of `agent.run()` for the **app** to
     handle — and the web layer has no handler. Even a *within-run* agent
     rewind would surface as a run error on the AG-UI path today.
2. **Telemetry: the capability has never been exercised.** A Logfire query
   over the project's recorded history (30-day window spanning the
   deployment's entire life) finds **zero** spans or messages matching
   `checkpoint`/`rewind` — no `save_checkpoint`, no `list_checkpoints`, no
   `rewind_to`, from any human or any agent, ever. This is the "actual usage"
   the plan said the decision should match.
3. **"Required by forking" no longer binds the web layer.** agent-web forking
   is gated OFF by default (Phase 5.2). eval-optimizer's fork engine wires its
   **own** per-run `InMemoryCheckpointStore` for fork anchors — a per-run use
   that works today and is untouched by either option.
4. **Option A became cheap — but would not make the claim true.** Phase 5.1's
   server-only `state/` tree plus the vendor's public
   `FileCheckpointStore(directory)` means durable per-thread storage is a
   two-line wiring change. But durability alone yields *durable dead weight*:
   full message snapshots duplicated on disk (a second PII surface for 6.4 to
   account for, beyond history) feeding a rewind capability that has no UI, no
   web-layer `RewindRequested` handling, and no observed demand. Making
   ADR-0015's sentence TRUE requires all three — that is new feature work, not
   congruency repair.

## Decision

**Option B: checkpoints are per-run, deliberately.** The durable
cross-request rewind claim is withdrawn rather than implemented.

1. `InMemoryCheckpointStore()` per request in `make_deps` stays — now
   documented as the *intended* scope, not an accident. What remains true and
   supported: checkpoints exist **within a single run** (the store the fork
   machinery anchors on: pre/post-fork checkpoints), and per-thread isolation
   holds (each request's store is its own object).
2. ADR-0015's checkpointing row is annotated as corrected by this ADR (the
   house pattern: newer ADRs supersede inline, never silent rewrites). Living
   docs (PDR/README) already avoid the durable-rewind claim after the gate-5
   sync; any residual claim found is aligned in the implementation commit.
3. The unhandled-`RewindRequested` limitation is **recorded, not hidden**: if
   an agent ever invokes `rewind_to` on the web path, the run errors. This is
   acceptable for a tool nothing has ever called — and it is the telemetry
   tripwire below.
4. ISSUE-1 closes with this ADR.

**Revisit trigger (recorded):** implement Option A — `FileCheckpointStore`
under `state/checkpoints/<slug>/` (the 5.1 tree keeps it outside every
agent-writable root), plus a web-layer `RewindRequested` handler and a UI
affordance — when either (a) a user actually asks to resume/rewind across
requests, or (b) telemetry shows agents attempting `rewind_to`/
`save_checkpoint` on the web path. The 5.1 tree exists precisely so that
upgrade is small and well-understood.

Options rejected:

- **Option A now** — rejected on evidence: zero usage ever, no UI, no rewind
  handler; durability alone moves the falsehood ("durable rewind" that errors
  when invoked) instead of removing it, while growing the server-side PII
  surface ahead of the 6.4 posture ADR.
- **Rip out checkpointing entirely** (`include_checkpoints=False`) — rejected:
  the per-run store is genuinely load-bearing for fork anchoring (both
  projects), and the capability costs nothing when unused.

## Consequences

- The critique's top congruency finding resolves with **prose + intent**, not
  new machinery: the code was right; the claim was wrong. Matrix D is
  untouched (no new files — exactly the plan's stated parity impact for B);
  Matrix A/B/C unaffected.
- `crit-checkpoint-persistence` flips to `changed` with a named test pinning
  the now-deliberate per-run scope (fresh store per request), alongside the
  existing round-trip/isolation test; `verified_by` prose covers the doc
  alignment. Gate 2 protocol as always.
- ADR-0015 gains an inline correction pointer; its other rows stand.
- A future Option A upgrade has a pre-planned shape (state tree, public
  store class, named trigger) instead of an ambient "someday."

## Implementation sketch (lands only after this ADR is Accepted)

`deps.py`: comment the per-request `InMemoryCheckpointStore` as ADR-0019
intent. `test_deps_factory.py` (or `test_checkpoints.py`): add
`test_checkpoint_store_is_per_run_by_design` (same thread, two requests, two
independent empty stores). `docs/adr/0015`: annotate the checkpointing row
"scope corrected by ADR-0019". Sweep PDR/README/HANDOFF-living-docs for any
residual durable-rewind claim. `docs/ISSUES.md`: close ISSUE-1. Manifest:
`crit-checkpoint-persistence` → `changed` in the same commit.
