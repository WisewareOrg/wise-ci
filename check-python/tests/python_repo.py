"""Builds the git repositories check-python's tests run against, each with its own `.venv`.

Each repository is in its own temporary directory.

`env(**overrides)` returns a subprocess environment with the machine's own git configuration shut
out and a fixed identity (docs/TESTING.md "Real dependencies where possible").

`make_repo(directory, seeds, venv, tracked_files, ignored_files, python)` runs `git init` at `directory`,
writes the clean project (CLEAN) plus one file per seed named in `seeds`, creates `.venv` with
`uv venv` unless `venv` is false (the project has no dependencies, so it is synced as created),
gitignores `.venv`, and `git add`s the rest so `git ls-files '*.py'` sees every Python file. The
clean project passes every tool; each seed in SEEDS is one file that trips exactly one tool and no
other. `tracked_files` adds further tracked files (for nested paths); `ignored_files` writes files
that `.gitignore` excludes; `python=False` drops the clean project's Python file.
"""

import os
import subprocess
import sys
from pathlib import Path

_ISOLATION = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-python tests",
    "GIT_AUTHOR_EMAIL": "check-python-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-python tests",
    "GIT_COMMITTER_EMAIL": "check-python-tests@wise-ci.invalid",
}

CLEAN = {
    "pyproject.toml": '[project]\nname = "fixture"\nversion = "0"\nrequires-python = ">=3.12"\n',
    ".gitignore": ".venv/\n",
    "clean.py": '''"""A module every tool passes."""


def add(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: The first number.
        b: The second number.

    Returns:
        The sum.
    """
    return a + b
''',
}

# seed name -> (file name, text). Each trips its own tool only.
SEEDS = {
    "ruff check": (
        "seed_ruff_check.py",
        '"""An unused import."""\n\nimport os\n',
    ),
    "ruff format": (
        "seed_ruff_format.py",
        '"""A string ruff format would requote."""\n\nVALUE = \'single\'\n',
    ),
    "interrogate": (
        "seed_interrogate.py",
        '"""A function with no docstring."""\n\n\ndef undocumented() -> int:\n    return 1\n',
    ),
    "pydoclint": (
        "seed_pydoclint.py",
        '''"""A docstring whose Args section names an argument the function lacks."""


def mismatched(x: int) -> int:
    """Return x.

    Args:
        y: Not an argument.

    Returns:
        x.
    """
    return x
''',
    ),
    "ty": (
        "seed_ty.py",
        '''"""A return value of the wrong type."""


def wrong() -> int:
    """Return an int.

    Returns:
        Not an int.
    """
    return "text"
''',
    ),
}


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
    result.pop("VIRTUAL_ENV", None)
    result.update(overrides)
    return result


def _run(directory: Path, *args: str) -> None:
    """Run a command in a directory, asserting it succeeds.

    Args:
        directory: The working directory.
        *args: The command and its arguments.
    """
    result = subprocess.run(list(args), cwd=directory, env=env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def make_repo(
    directory: Path,
    seeds: tuple[str, ...] = (),
    venv: bool = True,
    tracked_files: dict[str, str] | None = None,
    ignored_files: dict[str, str] | None = None,
    python: bool = True,
) -> Path:
    """Create a git repository holding the clean project and the named seeds.

    Args:
        directory: Where to create it.
        seeds: Names in SEEDS whose files to add.
        venv: Whether to create `.venv`.
        tracked_files: Further files to write and track, as path to text.
        ignored_files: Files to write under a gitignored path, as path to text.
        python: False to leave out the clean project's Python file.

    Returns:
        The repository directory.
    """
    directory.mkdir(parents=True, exist_ok=True)
    _run(directory, "git", "init", "-q", "-b", "main")
    for name, text in CLEAN.items():
        if name.endswith(".py") and not python:
            continue
        (directory / name).write_text(text)
    for seed in seeds:
        name, text = SEEDS[seed]
        (directory / name).write_text(text)
    for relpath, text in {**(tracked_files or {}), **(ignored_files or {})}.items():
        path = directory / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    with (directory / ".gitignore").open("a") as gitignore:
        gitignore.writelines(f"{relpath}\n" for relpath in ignored_files or {})
    if venv:
        _run(directory, "uv", "venv", "-q", "--python", sys.executable, ".venv")
    _run(directory, "git", "add", "-A")
    return directory
