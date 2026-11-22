"""Builds the git repositories check-python-floor's tests run against, each in its own temporary
directory, and the pyproject.toml text they carry.

`env(**overrides)` returns a subprocess environment with the machine's own git configuration shut
out and a fixed identity (docs/TESTING.md "Real dependencies where possible").

`make_repo(directory, pyproject, tracked_py, untracked_py)` runs `git init` at `directory`, writes
`pyproject` as the root pyproject.toml when it is not None, writes `tracked_py` and `untracked_py`
as Python files, and `git add`s everything except the untracked ones, so `git ls-files '*.py'` sees
exactly `tracked_py`.

`pyproject(...)` returns the floor-conformant pyproject.toml text, with each knob a case turns to a
violation.
"""

import os
import subprocess
from pathlib import Path

_ISOLATION = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-python-floor tests",
    "GIT_AUTHOR_EMAIL": "check-python-floor-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-python-floor tests",
    "GIT_COMMITTER_EMAIL": "check-python-floor-tests@wise-ci.invalid",
}

CONFORMANT_SELECT = ["E", "F", "W", "I", "UP", "B", "SIM", "D", "D417"]


def env(**overrides: str) -> dict[str, str]:
    result = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result.update(_ISOLATION)
    result.update(_IDENTITY)
    result.pop("GITHUB_ACTIONS", None)
    result.update(overrides)
    return result


def git(directory: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(directory), *args], env=env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def make_repo(
    directory: Path,
    pyproject: str | None,
    tracked_py: tuple[str, ...] = ("module.py",),
    untracked_py: tuple[str, ...] = (),
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    git(directory, "init", "-q", "-b", "main")
    if pyproject is not None:
        (directory / "pyproject.toml").write_text(pyproject)
    for relpath in (*tracked_py, *untracked_py):
        path = directory / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Docstring."""\n')
    tracked = [*(["pyproject.toml"] if pyproject is not None else []), *tracked_py]
    if tracked:
        git(directory, "add", "--", *tracked)
    return directory


def _array(values: list[str]) -> str:
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


def pyproject(
    *,
    requires: str | None = ">=3.12",
    line_length: int = 120,
    select: list[str] = CONFORMANT_SELECT,
    convention: str = "google",
    src: str = '["src"]',
    ruff_extra: str = "",
    lint_extra: str = "",
    pydocstyle_extra: str = "",
    ruff: bool = True,
    tail: str = "",
) -> str:
    """The floor-conformant text by default; every keyword argument turns one thing."""
    project = '[project]\nname = "fixture"\nversion = "0"\n'
    if requires is not None:
        project += f'requires-python = "{requires}"\n'
    if not ruff:
        return f"{project}\n{tail}"
    return (
        f"{project}\n"
        f"[tool.ruff]\nline-length = {line_length}\nsrc = {src}\n{ruff_extra}\n"
        f"[tool.ruff.lint]\nselect = {_array(select)}\n{lint_extra}\n"
        f'[tool.ruff.lint.pydocstyle]\nconvention = "{convention}"\n{pydocstyle_extra}\n'
        f"{tail}"
    )
