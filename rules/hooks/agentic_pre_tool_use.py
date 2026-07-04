import json
import re
import sys


BLOCK_PATTERNS = [
    re.compile(r"(?i)(^|[\s;&|])pip\s+install\b"),
    re.compile(r"(?i)(^|[\s;&|])python\s+-m\s+pip\s+install\b"),
    re.compile(r"(?i)(^|[\s;&|])py\s+-[0-9.]+\s+-m\s+pip\s+install\b"),
]

ALLOW_HINTS = [
    "uv add",
    "uv run",
    "uv pip install",
    ".venv",
    "conda",
]


def _extract_command(payload: object) -> str:
    if isinstance(payload, dict):
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
            return tool_input["command"]
        for key in ("command", "cmd", "script"):
            if isinstance(payload.get(key), str):
                return payload[key]
    return json.dumps(payload, sort_keys=True)


def _deny(reason: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": raw}

    command = _extract_command(payload)
    command_lower = command.lower()
    if any(pattern.search(command) for pattern in BLOCK_PATTERNS):
        if not any(hint in command_lower for hint in ALLOW_HINTS):
            _deny(
                "Raw global pip installs are blocked by AgenticWork policy. "
                "Use 'uv add', 'uv run', or a documented project .venv workflow."
            )
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
