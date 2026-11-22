"""Checks the repository at the working directory against the org Python floor.

A repository tracking no `.py` file passes with a "no Python" line and its pyproject.toml is not
read. Otherwise a root pyproject.toml must exist and meet the allowlist constants below (`src` is
read but never judged). One stderr line per violation, in a fixed order; exit 1 if any.
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

LINE_LENGTH = 120
SELECT = ["E", "F", "W", "I", "UP", "B", "SIM", "D", "D417"]
CONVENTION = "google"
MIN_PYTHON = (3, 12)
FORBIDDEN_TABLES = ("ty", "interrogate", "pydoclint")

_RUFF_ALLOWED = {"line-length", "lint", "src"}
_LINT_ALLOWED = {"select", "pydocstyle"}
_PYDOCSTYLE_ALLOWED = {"convention"}
_LOWER_BOUND = re.compile(r"(?:>=|==|~=)\s*(\d+)\.(\d+)")


def _tracked_python() -> list[str]:
    """Returns the tracked `.py` files of the repository at the working directory."""
    out = subprocess.run(["git", "ls-files", "*.py"], capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def _extras(table: dict, allowed: set[str], path: str) -> list[str]:
    """Returns one violation per leaf of `table` outside `allowed`, descending into non-allowed tables."""
    lines = []
    for key, value in table.items():
        if key in allowed:
            continue
        if isinstance(value, dict) and value:
            lines += _extras(value, set(), f"{path}.{key}")
        else:
            lines.append(f"pyproject.toml: [{path}] {key}: not allowed by the floor")
    return lines


def _expected(path: str, key: str, table: dict, expected: object, text: str) -> list[str]:
    """Returns the violation for `key` in `table`, or nothing when it equals `expected`."""
    if key not in table:
        return [f"pyproject.toml: [{path}] {key}: missing, expected {text}"]
    if table[key] != expected:
        return [f"pyproject.toml: [{path}] {key}: expected {text}, found {json.dumps(table[key])}"]
    return []


def _requires_python(project: dict) -> list[str]:
    """Returns the violation for the `requires-python` lower bound, if any."""
    floor = ".".join(map(str, MIN_PYTHON))
    if "requires-python" not in project:
        return [f"pyproject.toml: [project] requires-python: missing, lower bound must be >= {floor}"]
    spec = project["requires-python"]
    match = _LOWER_BOUND.search(spec)
    if match is None or (int(match[1]), int(match[2])) < MIN_PYTHON:
        return [
            f"pyproject.toml: [project] requires-python: lower bound must be >= {floor}, found {json.dumps(spec)}"
        ]
    return []


def _select(lint: dict) -> list[str]:
    """Returns the violation for `select`, compared as a set."""
    expected = ", ".join(SELECT)
    if "select" not in lint:
        return [f"pyproject.toml: [tool.ruff.lint] select: missing, expected {expected}"]
    found = lint["select"]
    if set(found) != set(SELECT):
        return [
            f"pyproject.toml: [tool.ruff.lint] select: expected {expected} (any order), found {', '.join(found)}"
        ]
    return []


def violations(pyproject: dict) -> list[str]:
    """Returns every floor violation of a parsed pyproject.toml, in the fixed order."""
    tool = pyproject.get("tool", {})
    ruff = tool.get("ruff", {})
    lint = ruff.get("lint", {})
    pydocstyle = lint.get("pydocstyle", {})
    lines = _requires_python(pyproject.get("project", {}))
    lines += _expected("tool.ruff", "line-length", ruff, LINE_LENGTH, str(LINE_LENGTH))
    lines += _select(lint)
    lines += _expected(
        "tool.ruff.lint.pydocstyle", "convention", pydocstyle, CONVENTION, json.dumps(CONVENTION)
    )
    lines += _extras(ruff, _RUFF_ALLOWED, "tool.ruff")
    lines += _extras(lint, _LINT_ALLOWED, "tool.ruff.lint")
    lines += _extras(pydocstyle, _PYDOCSTYLE_ALLOWED, "tool.ruff.lint.pydocstyle")
    lines += [f"pyproject.toml: [tool.{name}] must be absent" for name in FORBIDDEN_TABLES if name in tool]
    return lines


def main() -> int:
    """Prints the verdict and returns the exit status."""
    tracked = _tracked_python()
    if not tracked:
        print("check-python-floor: no Python — no tracked .py files.")
        return 0
    path = Path("pyproject.toml")
    if not path.is_file():
        found = [f"pyproject.toml: missing at the repository root, but {len(tracked)} tracked .py file(s)"]
    else:
        try:
            found = violations(tomllib.loads(path.read_text()))
        except tomllib.TOMLDecodeError as error:
            found = [f"pyproject.toml: not valid TOML: {error}"]
    if not found:
        print("check-python-floor: pyproject.toml meets the floor.")
        return 0
    print("\n".join(found), file=sys.stderr)
    return 1
