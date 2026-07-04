# Vendored pydantic-deepagents — Runbook

What this is, how to run it on Windows with OpenRouter, and how to keep it updated.
Written 2026-07-01. Vendored from `github.com/vstorm-co/pydantic-deepagents` @ `f2224c5`
(version 0.3.34).

## What got vendored, and why

The full harness **source** now lives at:

```
C:\Users\pollm\AgenticWork\vendor\pydantic-deepagents\
```

This is the whole repository, not the trimmed PyPI package. The difference that
matters: the PyPI wheel does **not** ship the `apps/` directory, so the terminal
assistant (TUI) and the DeepResearch web app cannot be installed from pip at all.
They exist only here, under `apps/` (`cli`, `deepresearch`, `acp`, `harbor`).
Vendoring is what gives you those, plus the ability to edit any part of the harness.

One local edit has been applied (see "Vendor patch" below): a public
`ForkCoordinator.branch_outcomes()` accessor. Everything else is upstream-pristine.
The patch now exists as a formal diff — `vendor/patches/0001-branch-outcomes.patch`
(round-trip verified) — and provenance lives in `pydantic-deepagents/VENDOR.txt`.
The dead `.git/` and the in-tree `.venv/` were removed 2026-07-01 (parked in
`Obsolete/vendor-pydantic-deepagents/`): venvs are per-consumer now.

## Prerequisites

- **Python 3.10+** (3.11 or 3.12 recommended).
- **uv** (fast installer/venv manager). Install from https://docs.astral.sh/uv/ if needed.

## Install (Windows PowerShell) — post-pivot (ADR-0012)

**Each consumer owns its venv; nothing installs inside the vendored tree.**
Primary path — the AG-UI web service (`projects/agent-web`):

```powershell
cd C:\Users\pollm\AgenticWork\projects\agent-web
uv venv
uv pip install -e "..\..\vendor\pydantic-deepagents[web,mcp,yaml]" "pydantic-ai-slim[ag-ui]" -e .
```

`eval-optimizer` consolidates automatically: its `pyproject.toml` has
`[tool.uv.sources] pydantic-deep = { path = "../../vendor/pydantic-deepagents",
editable = true }`, so `uv sync` there installs from the vendor, never PyPI.

Optional extras: `.[sandbox]` (Docker execution backend), `.[browser]` (Playwright).
Avoid `.[all]` — it drags in TUI/ACP/liteparse. Note `ag-ui` is a **pydantic-ai**
extra, not a vendor extra.

### Legacy: TUI install (abandoned as the interface, ADR-0012)

```powershell
uv pip install -e ".[cli]"    # Textual TUI + openrouter/openai/duckduckgo bundle
```

## Verify the core

`verify_core.py` (in `vendor\`) confirms imports, that forking wires up, that the
vendor patch is live, and that the OpenRouter model path constructs. No network.

```powershell
uv run python ..\verify_core.py
```

Expect `CORE OK`. This is the check to re-run any time you upgrade or re-vendor.

## Wire OpenRouter

The harness natively understands the `openrouter:` model prefix — no custom code.

```powershell
setx OPENROUTER_API_KEY "sk-or-..."     # new shells pick it up; or put it in a .env
```

Then reference models as `openrouter:<slug>`, confirming exact slugs at
https://openrouter.ai/models — e.g. `openrouter:z-ai/glm-4.6`,
`openrouter:anthropic/claude-opus-4-6`, `openrouter:qwen/qwen-2.5-coder-32b-instruct`.

Model-stack note: agentic quality is driven mostly by the model, not the harness.
Put the strongest coding model you can afford on the **driver/generator** role;
reserve cheap models for narrow, low-judgment steps. Your own
`projects/eval-optimizer/docs/C5_FAILURE_DIAGNOSIS.md` (GLM 5.2 → all branches
non-viable) is a concrete reminder of what a too-weak driver produces.

## Launch the terminal assistant (TUI)

```powershell
uv run pydantic-deep tui --model openrouter:anthropic/claude-opus-4-6
```

Useful flags (from the README): `--sandbox docker` (run tools in a Docker sandbox),
`--workspace <name>` (named workspace whose packages persist), `--browser`
(Playwright browser automation). Slash commands, live fork panels (`/fork`,
`/merge`), and model switching are built into the TUI.

## DeepResearch app (later)

`apps/deepresearch/` is a separate web app (planner + parallel research subagents,
search-provider wiring such as Tavily/Brave/Jina, report export). It has its own
setup and env — treat it as a follow-on once the core + TUI are comfortable. See
`apps/deepresearch/README.md` in the vendored tree.

## Vendor patch: `ForkCoordinator.branch_outcomes()`

File: `pydantic_deep/features/forking/coordinator.py` (one added method, ~25 lines,
right above the private `_build_branch_outcomes`).

Why: the shipped public API exposes no per-branch `test_pass_ratio`; only the LLM
judge (`resolve()`) reads it internally via the private `_build_branch_outcomes()`.
Your evaluator/optimizer wants **deterministic** test-based selection. This accessor
exposes that evidence publicly so you can pick a winner without the judge:

```python
outcomes = await coordinator.branch_outcomes()
best = max(outcomes, key=lambda o: o.test_pass_ratio or -1.0)
await coordinator.merge_or_select(f"pick:{best.branch_id}")
```

Requires `test_command` set on the `LiveForkCapability` for `test_pass_ratio` to be
populated. This is the near-term realization of "Option A" from the fix plan; the
long-term move is to upstream the same method so your local diff drops to zero.

## Updating / re-vendoring later (IMPORTANT)

Git does **not** work inside `C:\Users\pollm\AgenticWork\` — that folder is a
special mount and git can't write its metadata there (you'll see "operation not
permitted"). Large writes into it can also truncate silently. The procedure is now
mechanical:

1. Clone fresh in a normal local folder, e.g. `C:\dev\pdda`:
   `git clone https://github.com/vstorm-co/pydantic-deepagents.git C:\dev\pdda`
2. Copy the tree into `vendor\pydantic-deepagents\` (excluding `.git`).
3. **Verify the copy:** `python vendor\revendor_check.py C:\dev\pdda`
   (sha256 + file-count over `pydantic_deep/**/*.py`; catches silent truncation).
4. **Re-apply the patch:** from `vendor\pydantic-deepagents\`:
   `git apply ..\patches\0001-branch-outcomes.patch` (run it in `C:\dev\pdda` first
   if you prefer patching before the copy; `patch -p1 <` works too).
5. Update `VENDOR.txt` (new commit SHA + date), re-run each consumer's install and
   `verify_core.py` from each consumer venv.
6. Check upstream `CHANGELOG.md` for `pydantic_ai.ui` / AG-UI adoption — if upstream
   grows its own AG-UI surface, `projects/agent-web` may shrink; don't write new
   glue without looking.

If upstream ever adds a public per-branch outcome API, drop the patch and switch
callers. Never park runtime dirs (`apps/deepresearch/workspace*`) in backups/sync.

## Consumers

Both projects install the harness **only** from this vendored tree (PDR
consolidation rule, 2026-07-01):

- `projects/eval-optimizer` — via `[tool.uv.sources]` in its `pyproject.toml`
  (`uv sync` does the right thing). Its `forking.py` can drop the private
  `_build_branch_outcomes()` call for the public `coordinator.branch_outcomes()`.
- `projects/agent-web` — editable install per the Install section above
  (AG-UI web service, ADR-0012…0016).
