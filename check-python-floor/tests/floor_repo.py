"""Builds the git repositories check-python-floor's tests run against, and the pyproject.toml text they carry.

Each repository is in its own temporary directory.

`env(**overrides)` returns a subprocess environment with the machine's own git configuration shut
out and a fixed identity (docs/TESTING.md "Real dependencies where possible").

`make_repo(directory, pyproject, tracked_py, untracked_py, extra_files)` runs `git init` at
`directory`, writes `pyproject` as the root pyproject.toml when it is not None, writes `tracked_py`
and `untracked_py` as Python files and `extra_files` (path to text) as tracked files, and `git
add`s everything except the untracked ones, so `git ls-files '*.py'` sees exactly `tracked_py`.

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
    """Build a subprocess environment isolated from the machine's git configuration.

    Args:
        **overrides: Variables set last, over the isolated environment.

    Returns:
        The environment mapping.
    """
    result = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result.update(_ISOLATION)
    result.update(_IDENTITY)
    result.pop("GITHUB_ACTIONS", None)
    result.update(overrides)
    return result


def git(directory: Path, *args: str) -> None:
    """Run git in a directory, asserting it succeeds.

    Args:
        directory: The repository.
        *args: The git arguments.
    """
    result = subprocess.run(["git", "-C", str(directory), *args], env=env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def make_repo(
    directory: Path,
    pyproject: str | None,
    tracked_py: tuple[str, ...] = ("module.py",),
    untracked_py: tuple[str, ...] = (),
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Create a git repository holding the given files.

    Args:
        directory: Where to create it.
        pyproject: The root pyproject.toml text, or None for none.
        tracked_py: Python files to write and track.
        untracked_py: Python files to write and leave untracked.
        extra_files: Other files to write and track, as path to text.

    Returns:
        The repository directory.
    """
    directory.mkdir(parents=True, exist_ok=True)
    git(directory, "init", "-q", "-b", "main")
    if pyproject is not None:
        (directory / "pyproject.toml").write_text(pyproject)
    for relpath in (*tracked_py, *untracked_py):
        path = directory / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Docstring."""\n')
    extra_files = extra_files or {}
    for relpath, text in extra_files.items():
        path = directory / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    tracked = [*(["pyproject.toml"] if pyproject is not None else []), *tracked_py, *extra_files]
    if tracked:
        git(directory, "add", "--", *tracked)
    return directory


def _array(values: list[str]) -> str:
    """Render strings as a TOML array.

    Args:
        values: The strings.

    Returns:
        The TOML array text.
    """
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
    """Build pyproject.toml text, floor-conformant by default; each argument turns one thing.

    Args:
        requires: The `requires-python` value, or None to omit the key.
        line_length: The ruff `line-length`.
        select: The ruff `lint.select` rules.
        convention: The pydocstyle convention.
        src: The ruff `src` value as TOML text.
        ruff_extra: Extra lines in `[tool.ruff]`.
        lint_extra: Extra lines in `[tool.ruff.lint]`.
        pydocstyle_extra: Extra lines in `[tool.ruff.lint.pydocstyle]`.
        ruff: False to omit the whole `[tool.ruff]` family.
        tail: Text appended after the ruff tables.

    Returns:
        The pyproject.toml text.
    """
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
