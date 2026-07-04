"""Sandboxed validation of a generated candidate (C4/C5 keystone).

Pipeline: parse files out of the generator's output -> write to a temp workspace
-> run syntax + ruff + pytest -> return a typed ValidationResult.

Execution runs in a throwaway Docker container (`--network none`) by default, so
LLM-generated code never runs on the host. Set VALIDATE_MODE=local to run on the
host instead (faster, ONLY for code you trust; needs ruff + pytest installed).

Build the sandbox image once:  docker build -t evalopt-sandbox infra/sandbox
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .schema import CheckResult, ValidationResult

_MARKER = re.compile(r"^#\s*={2,}\s*(.+?)\s*={2,}\s*$")   # "# === path/to/file.py ==="
_FENCE = re.compile(r"^\s*```")                            # markdown code fence line
_SANDBOX_IMAGE = os.environ.get("VALIDATE_SANDBOX_IMAGE", "evalopt-sandbox")

# Runner executed *inside* the workspace; prints one JSON line. Named with a
# leading underscore so pytest does not collect it as a test module.
_RUNNER_NAME = "_evalopt_runner.py"
_RUNNER_SRC = r'''
import json
import re
import subprocess
import sys

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)[-2000:]

syntax_rc, syntax_out = run([sys.executable, "-m", "compileall", "-q", "."])
lint_rc, lint_out = run(["ruff", "check", ".", "--extend-exclude", "_evalopt_runner.py"])
test_rc, test_out = run([sys.executable, "-m", "pytest", "-q", "--no-header"])

passed = int((re.search(r"(\d+) passed", test_out) or [0, 0])[1]) if re.search(r"(\d+) passed", test_out) else 0
failed = int((re.search(r"(\d+) failed", test_out) or [0, 0])[1]) if re.search(r"(\d+) failed", test_out) else 0
no_tests = "no tests ran" in test_out

print("@@EVALOPT@@" + json.dumps({
    "syntax": {"rc": syntax_rc, "out": syntax_out},
    "lint": {"rc": lint_rc, "out": lint_out},
    "tests": {"rc": test_rc, "out": test_out, "passed": passed,
              "failed": failed, "total": passed + failed, "no_tests": no_tests},
}))
'''


def parse_artifact(text: str) -> dict[str, str]:
    """Extract {relative_path: file_content} from a generator's response.

    Splits on `# === path ===` markers; drops prose before the first marker and
    strips surrounding ``` code fences. Robust to the prose+fenced output we saw
    from the generators.
    """
    files: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []

    def _store(name: str | None, lines: list[str]) -> None:
        if not name:
            return
        body = "\n".join(line for line in lines if not _FENCE.match(line)).strip()
        files[name] = (body + "\n") if body else ""

    for line in text.splitlines():
        m = _MARKER.match(line)
        if m:
            _store(current, buf)
            current, buf = m.group(1).strip(), []
        elif current is not None:
            buf.append(line)
    _store(current, buf)
    return files


def write_files(files: dict[str, str], workdir: str | Path) -> list[str]:
    """Write parsed files under workdir (creating subdirs); return written paths."""
    root = Path(workdir)
    written: list[str] = []
    for rel, content in files.items():
        # guard against path escapes from a malformed/malicious marker
        dest = (root / rel).resolve()
        if not str(dest).startswith(str(root.resolve())):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(rel)
    return written


def _run_local(workdir: str, timeout: int) -> str:
    """Run the checks on the host (trusted code only; needs ruff + pytest)."""
    proc = subprocess.run(
        [sys.executable, _RUNNER_NAME], cwd=workdir,
        capture_output=True, text=True, timeout=timeout,
    )
    return proc.stdout + proc.stderr


def _run_docker(workdir: str, timeout: int) -> str:
    """Run the checks in an isolated container via create + cp + start — NO bind
    mount (avoids the Windows/Docker-Desktop 'access denied' file-sharing error).
    Container is force-removed in finally; the host temp dir is removed by the
    caller. Nothing persists."""
    create = subprocess.run(
        ["docker", "create", "--network", "none", "-w", "/w",
         _SANDBOX_IMAGE, "python", _RUNNER_NAME],
        capture_output=True, text=True, timeout=60,
    )
    cid = create.stdout.strip()
    if not cid:
        raise RuntimeError(f"docker create failed: {(create.stdout + create.stderr)[-500:]}")
    try:
        subprocess.run(
            ["docker", "cp", os.path.join(workdir, "."), f"{cid}:/w"],
            capture_output=True, text=True, timeout=60, check=True,
        )
        proc = subprocess.run(
            ["docker", "start", "-a", cid],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.stdout + proc.stderr
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True, timeout=60)


def _checks_from_report(report: dict) -> tuple[list[CheckResult], int, int]:
    checks = [
        CheckResult(name="syntax", passed=report["syntax"]["rc"] == 0, detail=report["syntax"]["out"]),
        CheckResult(name="lint", passed=report["lint"]["rc"] == 0, detail=report["lint"]["out"]),
    ]
    t = report["tests"]
    tests_ok = t["rc"] == 0 and not t.get("no_tests", False)
    checks.append(CheckResult(name="tests", passed=tests_ok, detail=t["out"]))
    return checks, t.get("passed", 0), t.get("total", 0)


def validate_artifact(artifact: str, *, mode: str | None = None, timeout: int = 240) -> ValidationResult:
    """Parse, sandbox, and check a generator artifact. The headline signal for
    plan viability: did the generated code compile, lint, and pass its tests?"""
    mode = mode or os.environ.get("VALIDATE_MODE", "docker")
    files = parse_artifact(artifact)
    if not files:
        return ValidationResult(
            passed=False, runner=mode,
            checks=[CheckResult(name="parse", passed=False,
                                detail="no files parsed (no '# === path ===' markers found)")],
        )

    workdir = tempfile.mkdtemp(prefix="evalopt-validate-")
    try:
        written = write_files(files, workdir)
        (Path(workdir) / _RUNNER_NAME).write_text(_RUNNER_SRC, encoding="utf-8")

        out = _run_docker(workdir, timeout) if mode == "docker" else _run_local(workdir, timeout)
        marker = out.find("@@EVALOPT@@")
        if marker == -1:
            return ValidationResult(
                passed=False, runner=mode, files_written=written,
                checks=[CheckResult(name="runner", passed=False,
                                    detail=f"runner produced no report: {out[-1500:]}")],
            )
        report = json.loads(out[marker + len("@@EVALOPT@@"):].splitlines()[0])
        checks, tp, tt = _checks_from_report(report)
        return ValidationResult(
            passed=all(c.passed for c in checks), checks=checks,
            files_written=written, tests_passed=tp, tests_total=tt, runner=mode,
        )
    except subprocess.TimeoutExpired:
        return ValidationResult(passed=False, runner=mode, files_written=list(files),
                                checks=[CheckResult(name="runner", passed=False, detail=f"timeout after {timeout}s")])
    except FileNotFoundError as e:  # docker not installed / not on PATH
        return ValidationResult(passed=False, runner=mode, files_written=list(files),
                                checks=[CheckResult(name="runner", passed=False, detail=f"runner unavailable: {e}")])
    except Exception as e:  # docker create/cp errors, etc. — never leak, never leave files
        return ValidationResult(passed=False, runner=mode, files_written=list(files),
                                checks=[CheckResult(name="runner", passed=False, detail=f"runner error: {e}")])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
