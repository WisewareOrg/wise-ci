"""Checks the repository at the working directory against the org Python floor.

A repository tracking no `.py` file passes with a "no Python" line and its pyproject.toml is not
read. Otherwise a root pyproject.toml must exist and meet the allowlist constants below (`src` is
read but never judged). A tracked `ruff.toml`, `.ruff.toml` or `ty.toml`, and a `[tool.ruff]` or
`[tool.ty]` in a non-root pyproject.toml, are violations too. One stderr line per violation, in a
fixed order; exit 1 if any.
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
STRAY_FILES = ("ruff.toml", ".ruff.toml", "ty.toml")

_RUFF_ALLOWED = {"line-length", "lint", "src"}
_LINT_ALLOWED = {"select", "pydocstyle"}
_PYDOCSTYLE_ALLOWED = {"convention"}
_LOWER_BOUND = re.compile(r"(?:>=|==|~=)\s*(\d+)\.(\d+)")


def _tracked(pattern: str) -> list[str]:
    """List the tracked files matching a pathspec.

    Args:
        pattern: The git pathspec.

    Returns:
        The matching tracked paths of the repository at the working directory.
    """
    out = subprocess.run(["git", "ls-files", "-z", pattern], capture_output=True, text=True, check=True).stdout
    return [name for name in out.split("\0") if name]


def _load(path: Path) -> dict:
    """Parse a TOML file.

    Args:
        path: The file.

    Returns:
        The parsed table.
    """
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _stray_configuration() -> list[str]:
    """Find ruff or ty configuration the allowlist does not read.

    A `ruff.toml`, `.ruff.toml` or `ty.toml` anywhere, and a `[tool.ruff]` or `[tool.ty]` in a
    pyproject.toml below the root, would configure the tool without passing the allowlist.

    Returns:
        One violation line per such file or table.
    """
    lines = []
    for path in _tracked("*.toml"):
        name = Path(path).name
        if name in STRAY_FILES:
            lines.append(f"{path}: not allowed by the floor")
        elif name == "pyproject.toml" and path != name:
            try:
                tool = _load(Path(path)).get("tool", {})
            except tomllib.TOMLDecodeError as error:
                lines.append(f"{path}: not valid TOML: {error}")
                continue
            lines += [f"{path}: [tool.{table}] not allowed by the floor" for table in ("ruff", "ty") if table in tool]
    return lines


def _extras(table: dict, allowed: set[str], path: str) -> list[str]:
    """Find the leaves of a table outside its allowlist, descending into non-allowed tables.

    Args:
        table: The parsed table.
        allowed: The keys the floor allows in it.
        path: The table's dotted name.

    Returns:
        One violation line per leaf outside `allowed`.
    """
    lines = []
    for key, value in table.items():
        if key in allowed:
            continue
        if isinstance(value, dict) and value:
            lines += _extras(value, set(), f"{path}.{key}")
        else:
            lines.append(f"pyproject.toml: [{path}] {key}: not allowed by the floor")
    return lines


def _expected(path: str, key: str, table: dict, expected: object) -> list[str]:
    """Compare one key with the value the floor requires.

    Args:
        path: The table's dotted name.
        key: The key to compare.
        table: The parsed table.
        expected: The required value.

    Returns:
        The violation line, or nothing when the key equals `expected`.
    """
    text = json.dumps(expected)
    if key not in table:
        return [f"pyproject.toml: [{path}] {key}: missing, expected {text}"]
    if table[key] != expected:
        return [f"pyproject.toml: [{path}] {key}: expected {text}, found {json.dumps(table[key])}"]
    return []


def _requires_python(project: dict) -> list[str]:
    """Check the `requires-python` lower bound.

    Args:
        project: The parsed `[project]` table.

    Returns:
        The violation line, or nothing when the lower bound is at least the minimum.
    """
    floor = ".".join(map(str, MIN_PYTHON))
    if "requires-python" not in project:
        return [f"pyproject.toml: [project] requires-python: missing, lower bound must be >= {floor}"]
    spec = project["requires-python"]
    match = _LOWER_BOUND.search(spec)
    if match is None or (int(match[1]), int(match[2])) < MIN_PYTHON:
        return [f"pyproject.toml: [project] requires-python: lower bound must be >= {floor}, found {json.dumps(spec)}"]
    return []


def _select(lint: dict) -> list[str]:
    """Compare `select` with the required rules as a set.

    Args:
        lint: The parsed `[tool.ruff.lint]` table.

    Returns:
        The violation line, or nothing when the sets are equal.
    """
    expected = ", ".join(SELECT)
    if "select" not in lint:
        return [f"pyproject.toml: [tool.ruff.lint] select: missing, expected {expected}"]
    found = lint["select"]
    if set(found) != set(SELECT):
        return [f"pyproject.toml: [tool.ruff.lint] select: expected {expected} (any order), found {', '.join(found)}"]
    return []


def violations(pyproject: dict) -> list[str]:
    """Check a parsed pyproject.toml against the floor.

    Args:
        pyproject: The parsed file.

    Returns:
        Every violation line, in the fixed order.
    """
    tool = pyproject.get("tool", {})
    ruff = tool.get("ruff", {})
    lint = ruff.get("lint", {})
    pydocstyle = lint.get("pydocstyle", {})
    lines = _requires_python(pyproject.get("project", {}))
    lines += _expected("tool.ruff", "line-length", ruff, LINE_LENGTH)
    lines += _select(lint)
    lines += _expected("tool.ruff.lint.pydocstyle", "convention", pydocstyle, CONVENTION)
    lines += _extras(ruff, _RUFF_ALLOWED, "tool.ruff")
    lines += _extras(lint, _LINT_ALLOWED, "tool.ruff.lint")
    lines += _extras(pydocstyle, _PYDOCSTYLE_ALLOWED, "tool.ruff.lint.pydocstyle")
    lines += [f"pyproject.toml: [tool.{name}] must be absent" for name in FORBIDDEN_TABLES if name in tool]
    return lines


def main() -> int:
    """Print the verdict.

    Returns:
        The exit status: 1 if any violation was printed.
    """
    tracked = _tracked("*.py")
    if not tracked:
        print("check-python-floor: no Python — no tracked .py files.")
        return 0
    path = Path("pyproject.toml")
    if not path.is_file():
        found = [f"pyproject.toml: missing at the repository root, but {len(tracked)} tracked .py file(s)"]
    else:
        try:
            found = violations(_load(path))
        except tomllib.TOMLDecodeError as error:
            found = [f"pyproject.toml: not valid TOML: {error}"]
    found += _stray_configuration()
    if not found:
        print("check-python-floor: pyproject.toml meets the floor.")
        return 0
    print("\n".join(found), file=sys.stderr)
    return 1
