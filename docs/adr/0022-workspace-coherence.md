# ADR-0022 — Workspace coherence: one Python floor (3.12), the meta-workspace layer kept as tested advisory policy, pip guard hardened

**Status:** Proposed · 2026-07-06 · resolves plan step **6.6**
(`crit-python-floors`, `crit-aspirational-catalogs`, `crit-pip-hook`) ·
completes the Phase-6 ADR set (0017–0022) — the last decision before
exit gate 6.

## Context

Step 6.6 batches the workspace-level residue "so the meta-workspace concept
gets one deliberate yes/no instead of ambient decay." Three sub-findings,
with the facts verified against the tree and the operating machine:

**Python floors (`crit-python-floors`).** Five declared constraints, no
shared story:

| Tree | requires-python | Note |
|---|---|---|
| `projects/agent-web` | `>=3.10` | HANDOFF-era verification on 3.10 |
| `projects/eval-optimizer` | `>=3.11,<3.14` | cap of undemonstrated necessity |
| `evals/agentic-smoke` | `>=3.13,<3.15` | excludes the interpreter below |
| `vendor/pydantic-deepagents` | `>=3.10` | pristine, out of scope |
| `catalogs/models.yml` | `compatibility_python: "3.13.x"` | aspiration, not reality |

Verified reality: **both live venvs run CPython 3.12.8** (`pyvenv.cfg`), and
CI (`astral-sh/setup-uv` + per-project `uv sync`) pins nothing — every job
lets uv satisfy each project's own floor independently. So the one
interpreter everything actually runs on is the one the smoke eval's floor
*forbids* and the catalog doesn't *name*. No floor encodes an engineering
constraint; they are three authorship moments, not three requirements.

**The scaffolding layer (`crit-aspirational-catalogs`).** The critique read
`catalogs/scaffolds.yml`'s `root: ${AGENTIC_SCAFFOLDS}` as "an environment
variable defined nowhere in the repository" — true, and incomplete. Verified
on the operating machine: `AGENTIC_SCAFFOLDS` **is a machine-level USER
environment variable** pointing at `<agentic-work-root>\scaffolds`, and the
operator's global agent instructions (user-level CLAUDE.md) direct every
agent to search it before writing new framework, UI, agent, notebook, or
tool code. The meta-workspace concept is live *machine policy*; what is dead
is the repo's carriage of it: no project consumes the catalogs, `tools.yml`
blesses stacks (nicegui/streamlit/gradio/marimo) that appear in no project,
and `evals/agentic-smoke` — which smoke-tests the policy itself (imports
resolve under uv; pydantic-ai structured output works on `TestModel`) — is
referenced by nothing and runs in no CI job. `models.yml` has additionally
drifted from decided facts: it catalogs nvidia/local/openai/anthropic and
omits **openrouter, the workspace's sole decided live provider**
(step 3.4, ADR-0003).

**The pip guard (`crit-pip-hook`).** `rules/hooks/agentic_pre_tool_use.py`
denies `pip install` variants via regex — then waives the denial if any of
five substrings (`uv add`, `uv run`, `uv pip install`, `.venv`, `conda`)
appears *anywhere in the command string*, so `pip install requests # .venv`
passes. It has no tests, and eval-optimizer's AGENTS.md — injected into
every agent — calls the policy "Enforced". The claim exceeds the mechanism
twice over: the matcher is bypassable by construction, and the hook only
exists in harnesses that load it.

**Governing constraints.** ADR-0021's preservation tiers bind any "delete"
outcome (`Obsolete/` = dead + local-only; `legacy/` = deferred + committed).
Gate 2 requires every manifest flip to `changed` to name a passing test. All
three findings sit in `parity/manifest.yml` at `status: identical` pending
this ADR, with `matrix_rows: []` — none touches runtime parity.

## Decision

**Meta-ruling — the deliberate yes.** The meta-workspace layer (`catalogs/`,
`rules/`, `evals/`) is **kept and adopted as *tested, advisory policy***,
under one coherence rule that replaces aspiration: **every kept artifact is
either enforced by CI or explicitly marked advisory — nothing remains
implicit.** Harness2's committed copies become the canonical,
version-controlled home of the layer; the loose machine copies are
reference, not source.

1. **One Python floor: `requires-python = ">=3.12"`** in all three
   first-party projects. The two upper caps drop unless `uv lock`
   demonstrates a dependency that demands one — in which case the cap is
   retained *uniformly*, with the forcing dependency named in-file (a cap
   with a cited reason is policy; a cap without one is sediment). A root
   **`.python-version`** (`3.12`) pins interpreter selection so local uv and
   CI's setup-uv resolve identically with no per-job pins. `models.yml`
   moves [D→C]: `compatibility_python: "3.12.x"` (the verified floor);
   3.13/3.14 remain the experiment tier. Vendor stays pristine at `>=3.10`
   (satisfied by 3.12).
2. **Catalogs kept; the external contract documented; drift synced.**
   `scaffolds.yml` gains a header declaring its contract: `AGENTIC_SCAFFOLDS`
   is a machine-level USER env var; unset means the scaffold policy is
   inactive on that machine. This converts "undefined root" into "documented
   external dependency" without reintroducing a personal path (1.5 scrub
   stands). `tools.yml` is marked advisory in-file. `models.yml` adds
   openrouter as the decided default provider (ADR-0003 / step 3.4).
3. **`evals/agentic-smoke` is repurposed into the workspace-policy test
   project** — the layer's functional anchor. It keeps its import smokes and
   gains two suites: `test_pip_hook.py` (the documented bypasses must deny —
   comment-smuggled `.venv`, `pip install` after `;`/`&&`, `python -m pip`;
   the legitimate forms must pass — `uv add`, `uv run`, `uv pip install`)
   and `test_workspace_coherence.py` (all three pyprojects declare the
   identical floor; `models.yml` compatibility matches it; openrouter
   present). CI's `test` job gains the third project. The unused heavyweight
   dependency (`jupyter`) drops from its pyproject. Future floor drift is
   thereby a CI failure, not a rediscovery.
4. **The pip guard is hardened, and its claim is scoped.** The matcher moves
   from substring hints to tokenized parsing (`shlex`): decide from the
   parsed argv — program plus subcommand — so `pip install …` denies
   regardless of trailing comments, and `uv pip install` passes because the
   tokenized program is `uv`. `ALLOW_HINTS` is deleted. If tokenization
   fails (PowerShell-flavored input), fall back to the regex deny with *no*
   allow-waiver — fail toward denial, never toward bypass. AGENTS.md's
   "Enforced" line is re-scoped to name the mechanism honestly: enforced by
   the pre-tool-use hook in harnesses that load it; the policy binds
   everywhere. (Not a safety-claim downgrade: the guard is environment
   hygiene, not a Phase-5/6 security surface — and the mechanism itself gets
   strictly stronger.)

## Consequences

- Exit gate 6 unblocks on the ADR axis: 0017–0022 complete the six Phase-6
  decisions (6.1→0018, 6.2→0017, 6.3→0019, 6.4→0020, 6.5→0021, 6.6→0022).
- The three manifest entries flip to `changed`, each naming tests in the
  repurposed smoke project; `matrix_rows` stay empty — no runtime behavior
  change in either live project (both already run 3.12.8; floors are
  resolution metadata). Parity Matrices A–E are untouched.
- `uv.lock` regenerates in all three projects (changed resolution
  envelopes); the green suites are the proof nothing moved.
- The layer stops being critique-bait: the only unreferenced project becomes
  the thing that enforces the layer.
- What becomes harder: syncing the live projects on 3.10/3.11 interpreters.
  No known consumer does; the fork targets this machine plus CI, and vendor
  compatibility is unaffected.
- Revisit triggers: the deferred Gen-1 integration resuming (ADR-0021), or a
  wanted 3.13+-only feature — either re-opens the floor with this ADR as the
  baseline.

## Alternatives rejected

- **Floor 3.13 (the catalog's number).** Requires rebuilding both live venvs
  and re-verifying against live baselines captured on 3.12.8, immediately
  before the final live parity session — verification noise for zero
  functional payoff. [D→C]: the catalog moves to verified reality, not
  reality to the catalog.
- **Stated divergence (keep three floors, document why).** There is no
  "why" — the divergence is uncoordinated authorship, not engineering.
  Documenting it would launder decay as decision, the exact failure mode 6.6
  exists to stop.
- **Park the layer to `Obsolete/` / quarantine to `legacy/`.** The concept
  is live machine policy (a real env var, actively referenced by the
  operator's global agent instructions); parking would make the repo's
  self-description *less* true, not more. It also fits neither ADR-0021
  tier: not dead, not a deferred code substrate.
- **Adopt as machinery (projects read catalogs at runtime).** Over-
  engineering: no project needs catalog-driven behavior, and it would
  convert advisory documentation into a new runtime surface owing its own
  parity story.
- **Re-describe the hook as advisory without hardening.** Honest but lazy:
  the bypass costs ~20 lines to close, and this refactor's whole method is
  mechanism over prose. Conversely, hardening *without* scoping the claim
  leaves "Enforced" overstating where the hook exists at all. Both halves,
  not either.
- **Delete the hook.** It is the rules layer's only executable enforcement;
  removal trades a modest real control for nothing.

## Implementation sketch

One PR. Gate 1 tiers: behavioral for
`rules/hooks/agentic_pre_tool_use.py` and the three `pyproject.toml`s
(manifest entries named below); docs-tier for the yml/md edits.

- `pyproject.toml` ×3 → `requires-python = ">=3.12"`; caps dropped (or
  retained uniformly with the forcing dep named, per Decision 1); root
  `.python-version` = `3.12`; `uv lock` refresh ×3; agentic-smoke drops
  `jupyter`.
- `catalogs/models.yml`: `compatibility_python: "3.12.x"` + openrouter
  provider entry. `catalogs/scaffolds.yml`: env-contract header.
  `catalogs/tools.yml`: advisory header.
- `rules/hooks/agentic_pre_tool_use.py`: shlex-tokenized matcher,
  `ALLOW_HINTS` removed, deny-on-unparseable fallback.
- `evals/agentic-smoke/tests/`: `test_pip_hook.py`,
  `test_workspace_coherence.py`.
- `.github/workflows/harnessgates.yml`: `test` job gains
  `evals/agentic-smoke` (validate the YAML before commit, standing rule 7).
- `projects/eval-optimizer/AGENTS.md`: scope the "Enforced" line.
- `parity/manifest.yml`: `crit-python-floors`, `crit-aspirational-catalogs`,
  `crit-pip-hook` → `changed`, tests named.

Green: `uv run pytest -q` in all three projects, `uvx ruff check .`,
`uvx pyright src`, all gates.
