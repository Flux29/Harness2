# Python Environment Policy

## Defaults

- `uv` is the default Python environment and dependency manager.
- Global Python is a launcher/toolbox, not a project dependency store.
- Project dependencies belong in `pyproject.toml`, `uv.lock`, and a local `.venv`.

## Allowed Commands

- `uv init`
- `uv add <package>`
- `uv remove <package>`
- `uv sync`
- `uv run <command>`
- `uv pip install <package>` only when maintaining an existing pip-style project.

## Avoid

- `pip install <package>` against global Python.
- `python -m pip install <package>` against global Python.
- Installing agent, AI, data, or GUI packages system-wide.
- Using Anaconda base for agent work.

## Conda Exception

Use conda only when a project explicitly needs conda-managed binary, GPU, or non-Python dependencies. Create a named environment and document why conda is required.
