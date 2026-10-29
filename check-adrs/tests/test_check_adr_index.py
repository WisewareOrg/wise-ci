"""Specifies check-adrs/check-adr-index.py: every reporting path in both directions
(check-adrs/README.md).

Each case builds docs/decisions/ directly on disk in a temporary directory. The script makes no git
call, so no git repository is needed except for the one case that depends on that fact (an untracked
ADR file is still judged). The real script runs against it as a subprocess (docs/TESTING.md "Real
dependencies where possible").
"""

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-adr-index.py"

FILE_0001 = "0001-alpha.md"
FILE_0002 = "0002-beta.md"
HEADER = "# Architecture decision records\n\n| # | Rev | Decided | Decision |\n|---|---|---|---|\n"


def _row(number: str, target: str) -> str:
    return f"| [{number}]({target}) | 1 | 2026-01-01 | Decision {number} |\n"


def _index(*rows: str) -> str:
    return HEADER + "".join(rows)


BASE_FILES: dict[str, str] = {
    "docs/decisions/README.md": _index(_row("0001", FILE_0001), _row("0002", FILE_0002)),
    "docs/decisions/TEMPLATE.md": "# NNNN — Title\n",
    f"docs/decisions/{FILE_0001}": "# 0001 — Alpha\n",
    f"docs/decisions/{FILE_0002}": "# 0002 — Beta\n",
}

FAILED = "check-adr-index: the decisions directory and its index disagree"
PASSED = "and its index agree:"


def _write(repo: Path, files: dict[str, str]) -> None:
    for relpath, content in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _build(
    tmp_path: Path,
    overrides: dict[str, str | None],
    extra: Callable[[Path], None] | None = None,
) -> Path:
    """The base fixture overlaid with `overrides`; a None value drops that base file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {**BASE_FILES, **overrides}
    _write(repo, {path: content for path, content in files.items() if content is not None})
    if extra:
        extra(repo)
    return repo


def _run_check(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=repo, capture_output=True, text=True
    )


@dataclass(frozen=True)
class _Case:
    id: str
    overrides: dict[str, str | None]
    reports: list[str] = field(default_factory=list)
    extra: Callable[[Path], None] | None = None


MUST_FAIL: list[_Case] = [
    _Case(
        "adr-file-with-no-row",
        {"docs/decisions/0003-gamma.md": "# 0003 — Gamma\n"},
        ["docs/decisions/0003-gamma.md has no row in docs/decisions/README.md"],
    ),
    _Case(
        "row-naming-no-file",
        {"docs/decisions/README.md": _index(_row("0001", FILE_0001), _row("0002", FILE_0002), _row("0003", "0003-ghost.md"))},
        ["docs/decisions/README.md row 0003 names no ADR file"],
    ),
    _Case(
        "row-linking-the-wrong-filename",
        {f"docs/decisions/{FILE_0002}": None, "docs/decisions/0002-renamed.md": "# 0002 — Beta\n"},
        ["docs/decisions/README.md row 0002 links '0002-beta.md', but the file is '0002-renamed.md'"],
    ),
    _Case(
        "two-files-carrying-one-number",
        {"docs/decisions/0002-dup.md": "# 0002 — Dup\n"},
        ["number 0002 is carried by two files: 0002-beta.md, 0002-dup.md"],
    ),
    _Case(
        "two-rows-for-one-number",
        {"docs/decisions/README.md": _index(_row("0001", FILE_0001), _row("0002", FILE_0002), _row("0002", FILE_0002))},
        ["docs/decisions/README.md has two rows for number 0002"],
    ),
    _Case(
        "numbering-not-contiguous-from-0001",
        {
            f"docs/decisions/{FILE_0001}": None,
            "docs/decisions/0000-alpha.md": "# 0000 — Alpha\n",
            "docs/decisions/README.md": _index(_row("0000", "0000-alpha.md"), _row("0002", FILE_0002)),
        },
        ["ADR numbering is not contiguous from 0001: expected 0001, found 0000"],
    ),
    _Case(
        "file-not-named-nnnn-slug-md",
        {
            "docs/decisions/notes.md": "# Notes\n",
            "docs/decisions/00010-x.md": "# x\n",
        },
        [
            "docs/decisions/notes.md is not named NNNN-<slug>.md",
            "docs/decisions/00010-x.md is not named NNNN-<slug>.md",
        ],
    ),
    _Case(
        "a-directory-named-like-an-adr",
        {},
        ["docs/decisions/0003-notreal.md is not a readable file"],
        extra=lambda repo: (
            (repo / "docs/decisions/0003-notreal.md").mkdir(),
            (repo / "docs/decisions/0003-notreal.md/inside.txt").write_text("x\n"),
        ),
    ),
    _Case(
        "a-dangling-symlink-named-like-an-adr",
        {},
        ["docs/decisions/0004-ghost.md is not a readable file"],
        extra=lambda repo: (repo / "docs/decisions/0004-ghost.md").symlink_to(
            repo / "docs/decisions/0004-nonexistent.md"
        ),
    ),
]

MUST_PASS: list[_Case] = [
    _Case("the-index-as-it-stands", {}),
    _Case(
        "a-new-adr-plus-its-row",
        {
            "docs/decisions/0003-gamma.md": "# 0003 — Gamma\n",
            "docs/decisions/README.md": _index(
                _row("0001", FILE_0001), _row("0002", FILE_0002), _row("0003", "0003-gamma.md")
            ),
        },
    ),
    _Case("template-and-readme-skipped-by-name", {}),
    _Case(
        "a-non-md-file-and-a-subdirectory",
        {},
        extra=lambda repo: (
            (repo / "docs/decisions/notes.txt").write_text("scratch\n"),
            (repo / "docs/decisions/assets").mkdir(),
        ),
    ),
    _Case(
        "row-target-titled",
        {"docs/decisions/README.md": _index(f'| [0001]({FILE_0001} "Alpha") | 1 | 2026-01-01 | Decision 0001 |\n', _row("0002", FILE_0002))},
    ),
    _Case(
        "row-target-angle-bracketed",
        {"docs/decisions/README.md": _index(f"| [0001](<{FILE_0001}>) | 1 | 2026-01-01 | Decision 0001 |\n", _row("0002", FILE_0002))},
    ),
    _Case(
        "row-target-leading-dot-slash",
        {"docs/decisions/README.md": _index(f"| [0001](./{FILE_0001}) | 1 | 2026-01-01 | Decision 0001 |\n", _row("0002", FILE_0002))},
    ),
    _Case(
        "row-target-with-anchor",
        {"docs/decisions/README.md": _index(f"| [0001]({FILE_0001}#context) | 1 | 2026-01-01 | Decision 0001 |\n", _row("0002", FILE_0002))},
    ),
    _Case(
        "a-4-space-indented-example-row",
        {"docs/decisions/README.md": _index(_row("0001", FILE_0001), _row("0002", FILE_0002)) + "    " + _row("0009", "0009-nope.md")},
    ),
    _Case(
        "a-row-in-a-markdown-file-outside-decisions",
        {"docs/OTHER.md": _row("0009", "0009-nope.md")},
    ),
]


@pytest.mark.parametrize("case", MUST_FAIL, ids=lambda c: c.id)
def test_must_fail(case: _Case, tmp_path: Path) -> None:
    repo = _build(tmp_path, case.overrides, case.extra)
    result = _run_check(repo)
    assert result.returncode == 1
    assert FAILED in result.stderr
    for report in case.reports:
        assert report in result.stderr
    assert PASSED not in result.stdout


@pytest.mark.parametrize("case", MUST_PASS, ids=lambda c: c.id)
def test_must_pass(case: _Case, tmp_path: Path) -> None:
    repo = _build(tmp_path, case.overrides, case.extra)
    result = _run_check(repo)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert PASSED in result.stdout


def test_an_untracked_adr_file_with_no_row_is_still_judged(tmp_path: Path) -> None:
    """The population is the directory, os.listdir reports it like any other entry — unlike
    check-docs-index, no untracked guard is needed here (check-adrs/README.md)."""
    repo = _build(tmp_path, {})
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    init = subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, env=env, capture_output=True, text=True)
    assert init.returncode == 0, init.stderr

    (repo / "docs/decisions/0003-untracked.md").write_text("# 0003 — Untracked\n", encoding="utf-8")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo, env=env, capture_output=True, text=True
    )
    assert "?? docs/decisions/0003-untracked.md" in status.stdout

    result = _run_check(repo)
    assert result.returncode == 1
    assert "docs/decisions/0003-untracked.md has no row in docs/decisions/README.md" in result.stderr


def test_fenced_code_block_row_is_read_as_a_real_row(tmp_path: Path) -> None:
    """Known rejection (check-adrs/README.md): there is no fence blanking, so an illustrative
    example table in docs/decisions/README.md is read like any other row."""
    repo = _build(
        tmp_path,
        {
            "docs/decisions/README.md": _index(_row("0001", FILE_0001), _row("0002", FILE_0002))
            + "\n```\n"
            + _row("0009", "0009-example.md")
            + "```\n"
        },
    )
    result = _run_check(repo)
    assert result.returncode == 1
    assert "docs/decisions/README.md row 0009 names no ADR file" in result.stderr


def test_uppercase_extension_is_invisible_rather_than_rejected(tmp_path: Path) -> None:
    """Known gap (check-adrs/README.md): name.endswith(".md") is case-sensitive, so an ADR named
    with an uppercase extension is skipped rather than caught."""
    repo = _build(tmp_path, {})
    (repo / "docs/decisions/0003-upper.MD").write_text("# 0003 — Upper\n", encoding="utf-8")
    result = _run_check(repo)
    assert result.returncode == 0, result.stderr
    assert PASSED in result.stdout
