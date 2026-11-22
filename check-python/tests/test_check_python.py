"""Specifies check-python/check_python/__init__.py and its output interface as ruled in
~/.claude/deliverables/ca349fb5-0eba-40fc-849a-a8f9341652f1/i19-ruling-wiseci-output.md: ruff check,
ruff format, interrogate, pydoclint and ty each run, in that order, every run, against the
repository at the working directory (ty against its `.venv`); a `check-python: <name>` header
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
NOT_JUDGED = "not judged — no .venv at ./.venv; run uv sync first"

# Each pinned tool's own output when it fails the tool's seed, never when it passes (verified
# against the pins in docs and by the clean-repository case below).
MARKERS = {
    "ruff check": "F401",
    "ruff format": "would be reformatted",
    "interrogate": "FAILED",
    "pydoclint": "DOC103",
    "ty": "invalid-explicit-return",
}


def _run(repo: Path) -> tuple[int, str]:
    result = subprocess.run([str(SCRIPT)], cwd=repo, env=python_repo.env(), capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def _sections(output: str) -> dict[str, str]:
    """Maps each header's tool name to the text between it and the next header."""
    headers = list(HEADER.finditer(output))
    return {
        m.group(1): output[m.end() : headers[i + 1].start() if i + 1 < len(headers) else len(output)]
        for i, m in enumerate(headers)
    }


def test_clean_repository_passes_with_all_five_sections_in_order(tmp_path: Path) -> None:
    status, output = _run(python_repo.make_repo(tmp_path / "repo"))
    assert status == 0, output
    assert HEADER.findall(output) == list(TOOLS), output
    for tool, section in _sections(output).items():
        assert MARKERS[tool] not in section, (tool, output)
    assert "not judged" not in output


@pytest.mark.parametrize("seeded", TOOLS)
def test_one_seeded_defect_is_reported_by_its_own_tool_alone(tmp_path: Path, seeded: str) -> None:
    status, output = _run(python_repo.make_repo(tmp_path / "repo", (seeded,)))
    assert status == 1, output
    sections = _sections(output)
    assert list(sections) == list(TOOLS), output
    for tool in TOOLS:
        assert (MARKERS[tool] in sections[tool]) == (tool == seeded), (tool, output)
    assert python_repo.SEEDS[seeded][0] in sections[seeded], output


def test_every_tool_runs_even_when_earlier_ones_fail(tmp_path: Path) -> None:
    status, output = _run(python_repo.make_repo(tmp_path / "repo", tuple(python_repo.SEEDS)))
    assert status == 1, output
    sections = _sections(output)
    assert list(sections) == list(TOOLS), output
    for tool in TOOLS:
        assert MARKERS[tool] in sections[tool], (tool, output)
        assert python_repo.SEEDS[tool][0] in sections[tool], (tool, output)


def test_without_a_venv_ty_is_not_judged_and_the_other_tools_still_run(tmp_path: Path) -> None:
    status, output = _run(python_repo.make_repo(tmp_path / "repo", venv=False))
    assert status == 1, output
    sections = _sections(output)
    assert list(sections) == list(TOOLS), output
    assert NOT_JUDGED in sections["ty"].splitlines(), output
    for tool in TOOLS[:-1]:
        assert "not judged" not in sections[tool], (tool, output)
        assert sections[tool].strip(), (tool, output)
