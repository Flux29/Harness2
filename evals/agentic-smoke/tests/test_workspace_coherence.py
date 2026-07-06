"""Workspace coherence facts, CI-enforced (ADR-0022).

The meta-workspace layer's rule: every kept artifact is either enforced by CI
or explicitly marked advisory. These tests are the enforced half — one Python
floor across the first-party projects, the catalog matching verified reality,
and the decided provider present. Floor drift becomes a CI failure here, not
a rediscovery.
"""

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PYPROJECTS = [
    ROOT / "projects" / "agent-web" / "pyproject.toml",
    ROOT / "projects" / "eval-optimizer" / "pyproject.toml",
    ROOT / "evals" / "agentic-smoke" / "pyproject.toml",
]


def _requires_python(path: Path) -> str:
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]["requires-python"]


def _models_defaults() -> dict:
    models = yaml.safe_load((ROOT / "catalogs" / "models.yml").read_text(encoding="utf-8"))
    return models["defaults"]


def test_one_python_floor_across_first_party_projects() -> None:
    floors = {str(p.parent.name): _requires_python(p) for p in PYPROJECTS}
    assert len(set(floors.values())) == 1, f"floors diverged: {floors}"


def test_floor_matches_catalog_and_interpreter_pin() -> None:
    floor = _requires_python(PYPROJECTS[0])
    match = re.fullmatch(r">=(\d+\.\d+)", floor)
    assert match, f"floor must be a bare '>=X.Y' — a cap needs a named forcing dep (ADR-0022): {floor!r}"
    minor = match.group(1)
    assert _models_defaults()["compatibility_python"] == f"{minor}.x"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == minor


def test_floor_raise_target_stays_labeled() -> None:
    # ISSUE-6: 3.13 is the post-gate-6 target; until the raise lands it must be
    # recorded as target, distinct from the verified compatibility floor.
    defaults = _models_defaults()
    assert defaults["target_floor_python"] == "3.13.x"
    assert defaults["target_floor_python"] != defaults["compatibility_python"]


def test_models_catalog_names_the_decided_provider() -> None:
    models = yaml.safe_load((ROOT / "catalogs" / "models.yml").read_text(encoding="utf-8"))
    providers = models["providers"]
    assert "openrouter" in providers, "openrouter is the decided default (ADR-0003, step 3.4)"
    assert providers["openrouter"]["default_model"] == "z-ai/glm-5.2"
