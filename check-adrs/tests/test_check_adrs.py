"""Specifies check-adrs/check_adrs/__init__.py: the orchestrator that runs
check_adr_index.main() then check_adr_revs.main() even if the first half failed or crashed, and
exits 1 if either half failed (check-adrs/README.md; plan decision 3). The two halves' own
reporting paths are specified by test_check_adr_index.py and test_check_adr_revs.py; this file
specifies only what the orchestrator adds (nothing) and removes (a second Actions step).

Four cases run the installed `check-adrs` console script as a subprocess, against a combined
fixture tree built to satisfy -- or deliberately break -- both halves independently of each
other, since subprocessing only reaches the real action's entry point and cannot isolate one half
from the other the way test_check_adr_index.py and test_check_adr_revs.py do in-process. One case
-- a crash inside one half, which no filesystem fixture can cause in only one half, since a
missing docs/decisions crashes both -- runs in-process instead, with
check_adrs.check_adr_index.main monkeypatched to raise and check_adrs.check_adr_revs.main
monkeypatched to record whether it still ran.

No case spells a live citation (`ADR` followed by digits) as a literal string, for the same
reason test_check_adr_revs.py gives: every one is built at runtime from separate parts, so this
file's own text never reads as a citation when wise-ci's check-adrs gates wise-ci's own tree.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import check_adrs
import check_adrs.check_adr_index
import check_adrs.check_adr_revs

SCRIPT = Path(sys.executable).with_name("check-adrs")

ADR = "ADR"


def _cite(number: str, rev: int) -> str:
    """A prose citation, built from parts so this source never spells one literally."""
    return f"{ADR} {number} rev {rev}"


def _link(number: str, rev: int, target: str) -> str:
    return f"[{_cite(number, rev)}]({target})"


def _row(number: str, rev: int, target: str) -> str:
    return f"| [{number}]({target}) | {rev} | 2026-01-01 | Decision {number} |\n"


def _index(*rows: str) -> str:
    return "# Architecture decision records\n\n| # | Rev | Decided | Decision |\n|---|---|---|---|\n" + "".join(rows)


def _adr_text(number: str, rev: int = 1) -> str:
    changelog = "\n".join(
        f"- **rev {r}** — 2026-01-0{r} — first written (#1 ticket)." for r in range(1, rev + 1)
    )
    return (
        f"# {number} — Decision\n\n"
        "**Status:** accepted\n"
        "**Decided:** 2026-01-01\n"
        f"**Rev:** {rev}\n"
        "\n## Revisions\n\n"
        f"{changelog}"
        "\n\n## Context\n\nContext text.\n"
    )


FILE_0001 = "0001-decision.md"
FILE_0002 = "0002-decision.md"
FILE_0004 = "0004-decision.md"

# Satisfies both halves at once: contiguous, fully-indexed, revs-consistent ADRs, with one prose
# and one link citation, both current.
BASE_FILES: dict[str, str] = {
    "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002)),
    "docs/decisions/TEMPLATE.md": "# NNNN — Title\n",
    f"docs/decisions/{FILE_0001}": _adr_text("0001"),
    f"docs/decisions/{FILE_0002}": _adr_text("0002"),
    "CITATIONS.md": (
        f"Prose citation: {_cite('0001', 1)}.\n\n"
        f"Link citation: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"
    ),
}

# Breaks only check-adr-index: a third ADR, numbered 0004 (skipping 0003), with its own fully
# valid, current, indexed head -- check-adr-index alone enforces contiguous numbering, so this
# is a index-only problem; check-adr-revs only cross-checks that every ADR it reads has a row at
# all, which 0004 does.
INDEX_ONLY_BROKEN: dict[str, str] = {
    f"docs/decisions/{FILE_0004}": _adr_text("0004"),
    "docs/decisions/README.md": _index(
        _row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002), _row("0004", 1, FILE_0004)
    ),
}

# Breaks only check-adr-revs: the prose citation is stale (pins rev 2, current is rev 1); the
# link citation stays current, so both citation mechanisms are still judged at least once and
# this is the tree's only revs problem.
REVS_ONLY_BROKEN: dict[str, str] = {
    "CITATIONS.md": (
        f"Prose citation: {_cite('0001', 2)}.\n\n"
        f"Link citation: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"
    )
}

BOTH_BROKEN: dict[str, str] = {**INDEX_ONLY_BROKEN, **REVS_ONLY_BROKEN}

INDEX_FAILED = "check-adr-index: the decisions directory and its index disagree"
INDEX_PASSED = "and its index agree:"
REVS_FAILED_HEADER = "problem(s):"
REVS_PASSED = "every one pinning the current rev"

# The exact stderr each half prints, unchanged by the move into a package (plan: "Printed text
# unchanged"). Verified directly against check_adrs/check_adr_index.py and
# check_adrs/check_adr_revs.py run over this exact fixture, not assumed.
INDEX_BLOCK = (
    f"{INDEX_FAILED} (1):\n"
    "  ADR numbering is not contiguous from 0001: expected 0003, found 0004\n"
)
REVS_BLOCK = f"1 {REVS_FAILED_HEADER}\n  CITATIONS.md:1: pins {_cite('0001', 2)}, current is rev 1\n"

_ISOLATION = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-adrs tests",
    "GIT_AUTHOR_EMAIL": "check-adrs-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-adrs tests",
    "GIT_COMMITTER_EMAIL": "check-adrs-tests@wise-ci.invalid",
}


def _env(**overrides: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_ISOLATION)
    env.update(_IDENTITY)
    env.update(overrides)
    return env


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], env=_env(), capture_output=True, text=True)


def _write(repo: Path, files: dict[str, str]) -> None:
    for relpath, content in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _build(tmp_path: Path, overrides: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    init = subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], env=_env(), capture_output=True, text=True
    )
    assert init.returncode == 0, init.stderr
    _write(repo, {**BASE_FILES, **overrides})
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
    assert commit.returncode == 0, commit.stderr
    return repo


def _run_check(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT)], cwd=repo, env=_env(), capture_output=True, text=True)


def test_revs_half_still_runs_when_the_index_half_fails(tmp_path: Path) -> None:
    """Collapsing two Actions steps into one console script must not stop the revs half from
    running after the index half fails: its own pass output must appear, proving it ran to
    completion rather than the overall exit code merely happening to read 1 for an unrelated
    reason."""
    repo = _build(tmp_path, INDEX_ONLY_BROKEN)

    result = _run_check(repo)

    assert result.returncode == 1
    assert REVS_PASSED in result.stdout


@pytest.mark.parametrize(
    "overrides",
    [INDEX_ONLY_BROKEN, REVS_ONLY_BROKEN, BOTH_BROKEN],
    ids=["index-only", "revs-only", "both"],
)
def test_either_half_failing_exits_1(tmp_path: Path, overrides: dict[str, str]) -> None:
    repo = _build(tmp_path, overrides)

    result = _run_check(repo)

    assert result.returncode == 1


def test_both_halves_passing_exits_0(tmp_path: Path) -> None:
    repo = _build(tmp_path, {})

    result = _run_check(repo)

    assert result.returncode == 0, result.stderr
    assert INDEX_PASSED in result.stdout
    assert REVS_PASSED in result.stdout


def test_each_halfs_failure_text_appears_verbatim_with_no_added_prefix(tmp_path: Path) -> None:
    """The orchestrator prints nothing of its own (plan decision 3): stderr is exactly the index
    half's block followed by the revs half's block (the plan's call order), byte for byte -- a
    wrong implementation that prepended a label (e.g. "check-adrs: "), merged the two counts, or
    added a blank line between them would still satisfy a substring-only check but fails this
    exact-equality one."""
    repo = _build(tmp_path, BOTH_BROKEN)

    result = _run_check(repo)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == INDEX_BLOCK + REVS_BLOCK


def test_a_crash_in_the_index_half_still_runs_the_revs_half(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """No filesystem fixture crashes only one half (a missing docs/decisions crashes both), so
    this is in-process: check_adr_index.main is monkeypatched to raise, and check_adrs.main()
    must still call check_adr_revs.main() (monkeypatched to record), return 1, and print the
    traceback to stderr -- the same text Python prints for an uncaught exception (plan
    decision 3: `traceback.print_exc()`)."""

    def _boom() -> int:
        raise RuntimeError("index half exploded")

    revs_calls: list[bool] = []

    def _record_revs() -> int:
        revs_calls.append(True)
        return 0

    monkeypatch.setattr(check_adrs.check_adr_index, "main", _boom)
    monkeypatch.setattr(check_adrs.check_adr_revs, "main", _record_revs)

    result = check_adrs.main()

    assert result == 1
    assert revs_calls == [True]
    captured = capsys.readouterr()
    assert "Traceback" in captured.err
    assert "RuntimeError: index half exploded" in captured.err
