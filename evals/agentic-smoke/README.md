# Agentic Smoke — the workspace-policy test project

Repurposed by ADR-0022 as the meta-workspace layer's functional anchor. It
verifies three things, in CI (`test` job) on Linux and Windows:

- the blessed Python stack imports and works under a local `uv` environment
  (`test_math_smoke.py`, `test_pydantic_ai_smoke.py`);
- the pip guard (`rules/hooks/agentic_pre_tool_use.py`) denies its documented
  bypasses and passes the uv workflow (`test_pip_hook.py`);
- the workspace's coherence facts hold — one Python floor across the
  first-party projects, `catalogs/models.yml` matching verified reality, the
  decided provider present (`test_workspace_coherence.py`).

Run:

```powershell
uv sync
uv run pytest -q
```
