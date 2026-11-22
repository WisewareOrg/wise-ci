"""Specifies check-python/check_python/__init__.py and its output interface (check-python/README.md).

Ruff check, ruff format, interrogate, pydoclint and ty each run, in that order, every run, against
the repository at the working directory (ty against its `.venv`); a `check-python: <name>` header
precedes each tool's own output; the exit status is 1 if any tool failed or was not judged.

Each case builds a real, isolated git repository in a temporary directory with its own `.venv`
(python_repo.py), one seeded defect per tool, and runs the installed `check-python` console script
against it as a subprocess, working directory the repository (docs/TESTING.md "Real dependencies
where possible"). Each tool's section must carry that tool's own native failure marker for its own
seed and no tool's failure marker otherwise, so a section can neither pass for another's failure nor
report a seed it did not run. Nothing defective is committed to this repository.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import python_repo

SCRIPT = Path(sys.executable).with_name("check-python")

TOOLS = ("ruff check", "ruff format", "interrogate", "pydoclint", "ty")
HEADER = re.compile(r"^check-python: (.+)$", re.MULTILINE)
NO_PYTHON_LINE = "check-python: no Python — no tracked .py files."
NOT_JUDGED = "not judged — no .venv at ./.venv; run uv sync first"

# Each pinned tool's own output when it fails the tool's seed, never when it passes (verified against
# the versions pinned in check-python/pyproject.toml and by the clean-repository case below).
MARKERS = {
    "ruff check": "F401",
    "ruff format": "would be reformatted",
    "interrogate": "FAILED",
    "pydoclint": "DOC103",
    "ty": "invalid-explicit-return",
}


def _run(repo: Path) -> tuple[int, str]:
    """Run the check in a repository.

    Args:
        repo: The repository to run in.

    Returns:
        The exit status and the combined stdout and stderr.
    """
    result = subprocess.run([str(SCRIPT)], cwd=repo, env=python_repo.env(), capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def _sections(output: str) -> dict[str, str]:
    """Map each header's tool name to the text between it and the next header.

    Args:
        output: The check's combined stdout and stderr.

    Returns:
        The section text by tool name.
    """
    headers = list(HEADER.finditer(output))
    return {
        m.group(1): output[m.end() : headers[i + 1].start() if i + 1 < len(headers) else len(output)]
        for i, m in enumerate(headers)
    }


def test_clean_repository_passes_with_all_five_sections_in_order(tmp_path: Path) -> None:
    """A clean repository passes with all five sections in order and no tool failure marker.

    Args:
        tmp_path: A fresh temporary directory.
    """
    status, output = _run(python_repo.make_repo(tmp_path / "repo"))
    assert status == 0, output
    assert HEADER.findall(output) == list(TOOLS), output
    for tool, section in _sections(output).items():
        assert MARKERS[tool] not in section, (tool, output)
    assert "not judged" not in output


@pytest.mark.parametrize("seeded", TOOLS)
def test_one_seeded_defect_is_reported_by_its_own_tool_alone(tmp_path: Path, seeded: str) -> None:
    """One seeded defect is reported in its own tool's section and no other, with exit 1.

    Args:
        tmp_path: A fresh temporary directory.
        seeded: The tool whose seed the repository carries.
    """
    status, output = _run(python_repo.make_repo(tmp_path / "repo", (seeded,)))
    assert status == 1, output
    sections = _sections(output)
    assert list(sections) == list(TOOLS), output
    for tool in TOOLS:
        assert (MARKERS[tool] in sections[tool]) == (tool == seeded), (tool, output)
    assert python_repo.SEEDS[seeded][0] in sections[seeded], output


def test_every_tool_runs_even_when_earlier_ones_fail(tmp_path: Path) -> None:
    """Every tool runs and reports its own seed even when earlier tools fail.

    Args:
        tmp_path: A fresh temporary directory.
    """
    status, output = _run(python_repo.make_repo(tmp_path / "repo", tuple(python_repo.SEEDS)))
    assert status == 1, output
    sections = _sections(output)
    assert list(sections) == list(TOOLS), output
    for tool in TOOLS:
        assert MARKERS[tool] in sections[tool], (tool, output)
        assert python_repo.SEEDS[tool][0] in sections[tool], (tool, output)


def test_without_a_venv_ty_is_not_judged_and_the_other_tools_still_run(tmp_path: Path) -> None:
    """Without a `.venv`, ty is not judged, the exit is 1, and the other tools still run.

    Args:
        tmp_path: A fresh temporary directory.
    """
    status, output = _run(python_repo.make_repo(tmp_path / "repo", venv=False))
    assert status == 1, output
    sections = _sections(output)
    assert list(sections) == list(TOOLS), output
    assert NOT_JUDGED in sections["ty"].splitlines(), output
    for tool in TOOLS[:-1]:
        assert "not judged" not in sections[tool], (tool, output)
        assert sections[tool].strip(), (tool, output)


def test_a_nested_tracked_file_is_checked_by_every_tool(tmp_path: Path) -> None:
    """Interrogate and pydoclint cover a tracked file below the root, not only root files.

    Args:
        tmp_path: A fresh temporary directory.
    """
    nested = {
        "pkg/sub/test_undocumented.py": python_repo.SEEDS["interrogate"][1],
        "pkg/sub/test_mismatched.py": python_repo.SEEDS["pydoclint"][1],
    }
    status, output = _run(python_repo.make_repo(tmp_path / "repo", tracked_files=nested))
    assert status == 1, output
    sections = _sections(output)
    assert "pkg/sub/test_undocumented.py" in sections["interrogate"], output
    assert "pkg/sub/test_mismatched.py" in sections["pydoclint"], output


def test_an_ignored_python_file_is_in_no_section(tmp_path: Path) -> None:
    """A gitignored `.py` file with a defect for every tool is not checked by any of them.

    Args:
        tmp_path: A fresh temporary directory.
    """
    ignored = {f"ignored/{name}": text for name, text in python_repo.SEEDS.values()}
    status, output = _run(python_repo.make_repo(tmp_path / "repo", ignored_files=ignored))
    assert status == 0, output
    assert "ignored/" not in output, output
    for tool, section in _sections(output).items():
        assert MARKERS[tool] not in section, (tool, output)


@pytest.mark.parametrize("venv", [True, False], ids=["with a venv", "without a venv"])
def test_no_tracked_python_passes_with_the_no_python_line_and_runs_no_tool(tmp_path: Path, venv: bool) -> None:
    """A repository tracking no `.py` passes with only the no-Python line: no tool section, no not-judged line.

    Args:
        tmp_path: A fresh temporary directory.
        venv: Whether the repository has a `.venv`.
    """
    repo = python_repo.make_repo(tmp_path / "repo", venv=venv, python=False, ignored_files={"ignored/x.py": "x ="})
    status, output = _run(repo)
    assert status == 0, output
    assert output.splitlines() == [NO_PYTHON_LINE], output
