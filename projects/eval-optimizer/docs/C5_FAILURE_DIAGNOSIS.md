# C5 `fork_check` Failure — Diagnosis, Answers & Proposed Solutions

**Date:** 2026-06-30
**Run:** `uv run python -m eval_optimizer.fork_check` — GLM 5.2 via OpenRouter
**Result:** completed, **0 exceptions**, **all 3 branches non-viable**; ~22 min wall, 48 model calls (~"a couple dollars").
**Telemetry:** Logfire project `deep-agents`, trace pulled via the Logfire MCP.

---

## TL;DR
The run did **not** crash — it completed and produced unusable output. The root cause is a
**content-contract mismatch**: our pipeline expects each generator to *return the solution as a
text artifact*, but the generator is a full `create_deep_agent` autonomous agent that *performed
the task with tools* (wrote files into its own ephemeral workspace, ran commands, spawned
subagents) and returned a conversational summary. The validator was handed summaries, not code.
It is **not** caused by modifying the harness — we never altered harness internals; we
**misapplied** an autonomous agent to a constrained text-generation role.

---

## Q1 — Is it a mismatch between what the harness/agents produce and what the pipeline expects?
**Yes. This is the primary cause.**

**The pipeline's contract** (`forking.py` → `validate.py`):
1. `generator.run(prompt).output` is expected to be a **string** containing the full solution as
   files delimited by `# === path ===` markers.
2. `parse_artifact()` extracts those files → `validate_artifact()` writes them to a temp dir and
   runs syntax → ruff → pytest in Docker.

**What the harness actually produced** — from the trace, the generators used the *full* toolset:
`write_file` ×12, `execute` ×11, `ls` ×13, `glob` ×9, `read_file` ×6, `write_todos`,
`update_todo_statuses`, `start_monitor`, `run_in_background`, and **`task` ×3 (spawning subagents)**.
So each generator **built the project inside its own ephemeral harness workspace** and returned a
*summary message* — not a `# === path ===` artifact.

**Consequence (matches the run's report):**
- `iterative-stack`: `.output` had no file markers → **0 files parsed** → failed `parse`.
- `recursive`, `library-based`: parser scraped 4 *fragmentary* files out of the prose/summary →
  failed `syntax` + `lint` + `tests`.
- The real generated code (if any) lives in the agents' throwaway workspaces, which the validator
  never sees.

So the artifact the pipeline needs (text code) ≠ the artifact the harness emits (an agent
transcript/summary). A classic interface mismatch.

## Q2 — Is it a result of modifying the harness inappropriately?
**No.** Important distinctions:
- We use `create_deep_agent(...)` **as shipped** — no monkey-patching, no internal edits. (The brief
  bare-`Agent` experiment was fully reverted per ADR-0007; nothing of it persists.)
- The failure is **misapplication, not modification**: we pointed a *full autonomous coding agent*
  at a role that only needs "produce text." The harness did exactly what it is built to do — act
  autonomously with tools. We handed it the wrong tool for the job.
- It is also a **hybrid that satisfies neither valid design**: we let the agent write files (to a
  place we don't read) *and* we parse `.output` (which doesn't contain the files). Either pure
  design would work; the mix does not.
- This does **not** implicate the pydantic-graph control plane (ADR-0008) — orchestration is fine.
  The problem is the *agent configuration inside the nodes*.

---

## Evidence (Logfire trace)
- 0 exceptions this run; the only in-window exceptions (22:58Z, `get_uploads_summary`) are the
  *previous* deps-crash run, not this one.
- `chat z-ai/glm-5.2`: **48 calls**, ~**1,346s** cumulative model time vs ~**188s** actual HTTP →
  ~1,160s is GLM 5.2 `thinking`.
- `fork: plan`: a single **976s (16.3-min)** span — planner `thinking="high"`, one turn.
- `fork: branch`: 3 spans, ~636s; `execute_tool task` ×3 (subagents) +190s; dozens of per-tool
  model round-trips → the 48-call / multi-dollar blowout.
- `validate_check` passes independently → the Docker sandbox/validator is **correct**; it
  accurately judged the scraped junk as non-viable.

---

## Proposed Solutions

### Option A — *(recommended)* Make content-producing roles tool-less text emitters
Build Planner / Generator / Critic so their only action is to **return output** (no file / shell /
subagent / monitor tools). Then `.output` *is* the artifact and the existing parser/validator work
as designed.
- **A1:** bare `pydantic_ai.Agent(model, output_type=..., instructions=...)` — no tools.
- **A2:** `create_deep_agent(...)` with the action surface disabled (`include_subagents=False`,
  `include_todo=False`, `include_skills=False`, `web_search=False`, file/shell/sandbox tools off) —
  keep the harness wrapper but strip the tools, *if* the toggles fully remove the action surface.
- **Trade-off:** lose harness memory / cost-tracking on these roles (they don't need it). Reserve
  the full harness for a future **executor** role that genuinely *should* act.
- **ADR impact:** **revisit ADR-0007 for the content-producing roles specifically.** ADR-0007
  rejected bare agents partly to avoid confounders and because the failure then looked like *model
  capability* (a weak local 7B). We now have clean evidence on a capable model (GLM 5.2) that the
  **toolset itself** drives the misbehavior for these roles — so a tool-less generator is the right
  call here, distinct from the harness-vs-bare debate for genuinely tool-using roles.

### Option B — Embrace file-writing: validate the agent's workspace, not `.output`
Point the harness's sandbox/workspace at a directory we own; after the run, validate *that
directory* instead of parsing `.output`.
- Aligns with the harness's intended design (agents write files).
- **Cons:** couples us to harness sandbox/filesystem internals; the subagent/`execute`/monitor
  wandering still wastes time and money; harder to keep deterministic for an evaluation engine.

### Option C — Autonomy & cost tuning *(necessary regardless; not sufficient alone)*
- Drop generator `thinking` to low/medium; reconsider planner `thinking="high"` (16 min/turn).
- Disable subagents/monitors/background tools; cap agent turns.
- Cuts the 22-min / 48-call blowout, but does **not** by itself fix the content mismatch — an agent
  that still has file tools may keep writing files instead of returning text.

### Recommendation
**A (tool-less content roles) + C (reasoning/turn caps).** A fixes the interface mismatch (the
actual failure); C fixes the cost/latency blowout. B is viable only if we deliberately re-architect
around workspace-reading, which adds coupling we don't want for a deterministic evaluator. Keep the
pydantic-graph control plane and the Docker validator unchanged.

### How we'd validate the fix (when implemented)
1. `generator_check` → `.output` contains `# === path ===` files; parses to N>0 files.
2. `validate_check` → unchanged (already green).
3. `fork_check` → ≥1 viable branch; minutes not tens-of-minutes; ~4–8 model calls, not ~48.
4. Logfire confirms: **no** `execute_tool task/execute/write_file/...` spans under the generators;
   short branch spans.

---

## One-line root cause
The Planner and Generators are full `create_deep_agent` autonomous agents with the complete
tool/subagent harness, so they *executed the task with tools inside their own workspaces* instead
of *returning the code as a text artifact* — leaving the parser/validator nothing valid to evaluate,
while the agentic tool-loop + GLM 5.2 `thinking` consumed ~22 min and 48 model calls. The harness
was used unmodified; the error was applying an autonomous agent to a text-emitter role.
