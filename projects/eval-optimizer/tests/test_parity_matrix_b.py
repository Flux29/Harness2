"""Parity Matrix B — HarnessForkReport / HarnessBranchResult (eval-optimizer).

Lives in this project's suite because the shared parity/ harness runs under the
agent-web venv, where eval_optimizer is not importable. Reads the committed v1
baseline schema and asserts field-shape parity. Rows that later steps flip
(selection_path added in 4.5; any_viable redefined in 6.x) are additive/semantic
and are re-pinned in those steps' commits.
"""
from __future__ import annotations

import json
from pathlib import Path

from eval_optimizer.schema import HarnessBranchResult, HarnessForkReport

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "baseline" / "schemas-v1"


def _baseline(name: str) -> dict:
    return json.loads((BASELINE / name).read_text(encoding="utf-8"))


def test_harness_fork_report_fields_additive_only():
    b = _baseline("harness-fork-report-schema.json")
    got = HarnessForkReport.model_json_schema()
    missing = set(b["properties"]) - set(got["properties"])
    assert not missing, f"Matrix B: HarnessForkReport dropped fields {missing}"


def test_harness_branch_result_fields_additive_only():
    b = _baseline("harness-branch-result-schema.json")
    got = HarnessBranchResult.model_json_schema()
    missing = set(b["properties"]) - set(got["properties"])
    assert not missing, f"Matrix B: HarnessBranchResult dropped fields {missing}"


def test_harness_fork_report_field_types_stable():
    """Field shapes (types) of the v1 fields must not change; only additions are
    allowed. selection_path (4.5) is an ADD, so this compares the intersection."""
    b = _baseline("harness-fork-report-schema.json")["properties"]
    got = HarnessForkReport.model_json_schema()["properties"]
    for field in b:
        assert got[field] == b[field], f"Matrix B: HarnessForkReport[{field}] shape drifted"
