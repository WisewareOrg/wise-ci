"""Runs the org Python gate against the repository at the working directory.

The tools and their order are in the check's README; every tool runs every time. A
`check-python: <name>` header precedes each tool's own output. interrogate and pydoclint receive
every tracked `.py` file; ruff and ty honour `.gitignore`. ty checks against `./.venv`; with none it
prints `not judged — ...` instead of running. Exits 1 if any tool failed or was not judged.
"""

import subprocess
import sys
from pathlib import Path

VENV = Path(".venv")

_PYDOCLINT_OPTIONS = [
    "--style=google",
    "--arg-type-hints-in-signature=True",
    "--arg-type-hints-in-docstring=False",
    "--check-return-types=False",
    "--skip-checking-short-docstrings=False",
    "--allow-init-docstring=True",
]


def _tool(name: str) -> str:
    """Locate a pinned tool.

    Args:
        name: The tool's executable name.

    Returns:
        The path of the tool installed beside the running interpreter.
    """
    return str(Path(sys.executable).with_name(name))


def main() -> int:
    """Run every tool under its header.

    A tool's stderr is merged into stdout so its text stays under its own header.

    Returns:
        The exit status: 1 if any tool failed or was not judged.
    """
    listing = subprocess.run(["git", "ls-files", "-z", "*.py"], capture_output=True, text=True, check=True).stdout
    tracked = [name for name in listing.split("\0") if name]
    tools = (
        ("ruff check", [_tool("ruff"), "check"]),
        ("ruff format", [_tool("ruff"), "format", "--check"]),
        ("interrogate", [_tool("interrogate"), "--fail-under", "100", "-vv", "--omit-covered-files", *tracked]),
        ("pydoclint", [_tool("pydoclint"), *_PYDOCLINT_OPTIONS, *tracked]),
        ("ty", [_tool("ty"), "check", "--python", str(VENV)]),
    )
    failed = False
    for name, command in tools:
        print(f"check-python: {name}", flush=True)
        if name == "ty" and not VENV.is_dir():
            print(f"not judged — no .venv at ./{VENV}; run uv sync first", flush=True)
            failed = True
        else:
            failed |= subprocess.run(command, stderr=subprocess.STDOUT).returncode != 0
    return int(failed)
