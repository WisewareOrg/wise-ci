"""Specifies check-adrs/check_adrs/check_adr_revs.py: every reporting path in both directions
(check-adrs/README.md).

Each case builds a real, isolated git repository in a temporary directory, over a minimal fixture
ADR tree — two ADRs and one citing document — rather than a copy of a real decisions directory, so a
case states its own premise. This half cannot be isolated from check-adr-index by subprocessing the
installed check-adrs script (that runs both halves), so it is run in-process instead: one shared
import of check_adrs.check_adr_revs, `monkeypatch.chdir` into each fixture, then `main()` called
directly and its return value and `capsys` output asserted; an exception the half does not catch
(outside a git repository) is asserted with `pytest.raises` instead of read back from stderr text.

No case spells a live citation (`ADR` followed by digits) as a literal string: every one is built at
runtime from separate parts, so this file's own text never reads as a citation when wise-ci's
check-adrs gates wise-ci's own tree.
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

import check_adrs.check_adr_revs as check_adr_revs

ADR = "ADR"


def _cite(number: str, rev: int | None = None) -> str:
    """A prose citation, built from parts so this source never spells one literally."""
    return f"{ADR} {number}" if rev is None else f"{ADR} {number} rev {rev}"


def _link(number: str, rev: int | None, target: str) -> str:
    return f"[{_cite(number, rev)}]({target})"


def _adr_text(
    number: str,
    rev: int = 1,
    title_number: str | None = None,
    changelog: list[int] | None = None,
    no_rev_line: bool = False,
    broken_rev_keyword: bool = False,
    no_title: bool = False,
    blank_lead: bool = False,
    bom: bool = False,
    continuation: str | None = None,
) -> str:
    title_number = number if title_number is None else title_number
    changelog = list(range(1, rev + 1)) if changelog is None else changelog
    revisions = "\n".join(f"- **rev {r}** — 2026-01-0{r} — first written (#1 ticket)." for r in changelog)
    rev_line = "" if no_rev_line else (f"**Broken:** {rev}\n" if broken_rev_keyword else f"**Rev:** {rev}\n")
    title = "" if no_title else f"# {title_number} — Decision\n\n"
    # `continuation`, when given, is a line placed directly after the changelog bullet, still
    # inside the Revisions section — an indented line continues it, an unindented one does not.
    text = (
        title
        + "**Status:** accepted\n"
        + "**Decided:** 2026-01-01\n"
        + rev_line
        + "\n## Revisions\n\n"
        + revisions
        + ("\n" + continuation if continuation is not None else "")
        + "\n\n## Context\n\nContext text.\n"
    )
    if blank_lead:
        text = "\n" + text
    if bom:
        text = "﻿" + text
    return text


def _row(number: str, rev: int | str, target: str) -> str:
    return f"| [{number}]({target}) | {rev} | 2026-01-01 | Decision {number} |\n"


def _index(*rows: str) -> str:
    return "# Architecture decision records\n\n| # | Rev | Decided | Decision |\n|---|---|---|---|\n" + "".join(rows)


FILE_0001 = "0001-decision.md"
FILE_0002 = "0002-decision.md"

BASE_FILES: dict[str, str] = {
    "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002)),
    "docs/decisions/TEMPLATE.md": "# NNNN — Title\n",
    f"docs/decisions/{FILE_0001}": _adr_text("0001"),
    f"docs/decisions/{FILE_0002}": _adr_text("0002"),
    "CITATIONS.md": (
        f"Prose citation: {_cite('0001', 1)}.\n\n"
        f"Link citation: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n\n"
        "A link to a non-ADR file: [see also](README.md).\n"
    ),
}

FAILED_HEADER = "problem(s):"
PASSED = "every one pinning the current rev"

_ISOLATION = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-adr-revs tests",
    "GIT_AUTHOR_EMAIL": "check-adr-revs-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-adr-revs tests",
    "GIT_COMMITTER_EMAIL": "check-adr-revs-tests@wise-ci.invalid",
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


def _build(
    tmp_path: Path,
    overrides: dict[str, str | None],
    untracked: dict[str, str] | None = None,
    extra: Callable[[Path], None] | None = None,
) -> Path:
    repo = tmp_path / "repo"
    init = subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], env=_env(), capture_output=True, text=True
    )
    assert init.returncode == 0, init.stderr
    files = {**BASE_FILES, **overrides}
    committed = {path: content for path, content in files.items() if content is not None}
    _write(repo, committed)
    if extra:
        extra(repo)
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
    assert commit.returncode == 0, commit.stderr
    if untracked:
        _write(repo, untracked)
    return repo


@dataclass(frozen=True)
class _Result:
    """Mirrors subprocess.CompletedProcess's three fields read below, so converting the call site
    is the only change every test needed -- not a rewrite of what each one asserts."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> _Result:
    # The script's own internal git calls (tracked/untracked) pass no env of their own, so they
    # inherit this process's environment -- in-process, that is the real os.environ, not a
    # subprocess's. _ISOLATION is applied the same way the fixture-building _git() calls get it,
    # so a case gives the same result on any machine and in CI (docs/TESTING.md), unchanged by
    # moving the invocation in-process.
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key, raising=False)
    for key, value in _ISOLATION.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(repo)
    returncode = check_adr_revs.main()
    captured = capsys.readouterr()
    return _Result(returncode, captured.out, captured.err)


def _assert_failed(result: _Result, reports: list[str]) -> None:
    assert result.returncode == 1, result.stdout
    assert FAILED_HEADER in result.stderr
    for report in reports:
        assert report in result.stderr
    assert PASSED not in result.stdout


def _assert_passed(result: _Result) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert PASSED in result.stdout


@dataclass(frozen=True)
class _Case:
    id: str
    overrides: dict[str, str | None] = field(default_factory=dict)
    reports: list[str] = field(default_factory=list)
    untracked: dict[str, str] = field(default_factory=dict)
    extra: Callable[[Path], None] | None = None


MUST_FAIL: list[_Case] = [
    _Case(
        "prose-citation-with-no-rev",
        {"CITATIONS.md": f"Prose citation: {_cite('0001')}.\n"},
        [f"cites {ADR} 0001 without a rev"],
    ),
    _Case(
        "prose-citation-pinning-a-stale-rev",
        {"CITATIONS.md": f"Prose citation: {_cite('0001', 2)}.\n"},
        [f"pins {ADR} 0001 rev 2, current is rev 1"],
    ),
    _Case(
        "link-titled-with-a-bare-number",
        {"CITATIONS.md": f"Link: [{_cite('0002')}](docs/decisions/{FILE_0002}).\n"},
        [f"is titled '{ADR} 0002', expected `{ADR} 0002 rev N`"],
    ),
    _Case(
        "link-title-naming-a-different-adr-than-it-targets",
        {"CITATIONS.md": f"Link: {_link('0001', 1, f'docs/decisions/{FILE_0002}')}.\n"},
        [f"link titled {ADR} 0001 targets {FILE_0002}"],
    ),
    _Case(
        "ordinary-prose-inside-a-revisions-section",
        {
            f"docs/decisions/{FILE_0001}": _adr_text(
                "0001",
                continuation=f"An ordinary sentence citing {_cite('0002')} without a rev.",
            )
        },
        [f"cites {ADR} 0002 without a rev"],
    ),
    _Case(
        "indented-continuation-of-ordinary-prose",
        {
            f"docs/decisions/{FILE_0001}": _adr_text(
                "0001",
                continuation=f"  continued, citing {_cite('0002')} without a rev",
            )
        },
        [f"cites {ADR} 0002 without a rev"],
    ),
    _Case(
        "changelog-continuation-naming-a-number-no-adr-carries",
        {
            f"docs/decisions/{FILE_0001}": _adr_text(
                "0001",
                continuation=f"  a continuation pinning {_cite('0009', 1)}, which does not exist",
            )
        },
        [f"cites {ADR} 0009, which is not an {ADR}"],
    ),
    _Case(
        "unpinned-citation-beside-a-correctly-titled-link",
        {"CITATIONS.md": f"See {_cite('0001')} and {_link('0001', 1, f'docs/decisions/{FILE_0001}')}.\n"},
        [f"cites {ADR} 0001 without a rev"],
    ),
    _Case(
        "a-stale-citation-in-an-index-rows-decision-cell",
        {
            "docs/decisions/README.md": _index(
                _row("0001", 1, FILE_0001),
                f"| [0002]({FILE_0002}) | 1 | 2026-01-01 | superseded by {_cite('0001', 2)} |\n",
            )
        },
        [f"pins {ADR} 0001 rev 2, current is rev 1"],
    ),
    _Case(
        "index-rev-column-disagreeing-with-the-adrs-head",
        {"docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002))},
        ["docs/decisions/README.md row 0002 says rev 2, its head says rev 1"],
    ),
    _Case(
        "adr-head-with-no-rev-line",
        {f"docs/decisions/{FILE_0001}": _adr_text("0001", no_rev_line=True)},
        ["declares 0 `**Rev:** N` lines, expected 1"],
    ),
    _Case(
        "adr-revved-with-no-changelog-line-for-the-new-rev",
        {
            f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2, changelog=[1]),
            "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002)),
            "CITATIONS.md": (
                f"Prose citation: {_cite('0001', 1)}.\n\n"
                f"Link citation: {_link('0002', 2, f'docs/decisions/{FILE_0002}')}.\n"
            ),
        },
        ["is at rev 2 but its Revisions section declares [1], expected one line per rev from 1"],
    ),
    _Case(
        "citation-of-a-number-no-adr-carries",
        {"CITATIONS.md": f"Prose citation: {_cite('0001', 1)}.\n\nAlso {_cite('0009', 1)}.\n"},
        [f"cites {ADR} 0009, which is not an {ADR}"],
    ),
    _Case(
        "a-plural-a-hyphen-and-the-wrong-case",
        {"CITATIONS.md": f"{ADR}s-0001 rev 1, and {ADR.lower()} 0001 rev 1.\n"},
        [f"is not a citation this can pin — write `{ADR} 0001 rev N`"],
    ),
    _Case(
        "an-underscore-a-hash-a-doubled-space-and-too-few-digits",
        {"CITATIONS.md": f"{ADR}_0001 rev 1, {ADR}#0001 rev 1, {ADR}  0001 rev 1, {ADR} 1 rev 1.\n"},
        [f"is not a citation this can pin — write `{ADR} 0001 rev N`"],
    ),
    _Case(
        "a-reference-style-link-and-a-raw-a-href",
        {
            "CITATIONS.md": (
                f"[ref]: docs/decisions/{FILE_0001}\n\n"
                f"Reference: [{_cite('0001', 1)}][ref].\n\n"
                f'Raw: <a href="docs/decisions/{FILE_0002}">{_cite("0002", 1)}</a>.\n'
            )
        },
        [
            f"cites an {ADR} as a reference-style link, which carries no rev",
            f"cites an {ADR} as a raw <a href>, which carries no rev",
        ],
    ),
    _Case(
        "a-link-to-an-adr-whose-title-carries-brackets",
        {"CITATIONS.md": f"[{_cite('0001', 1)} (see [elsewhere])](docs/decisions/{FILE_0001}).\n"},
        [f"is titled", "expected"],
    ),
    _Case(
        "a-link-to-an-adr-wrapped-across-two-lines",
        {"CITATIONS.md": f"See [{_cite('0001', 1)}\n](docs/decisions/{FILE_0001})\n"},
        ["has no title this can read"],
    ),
    _Case(
        "the-head-format-changed-everywhere-so-nothing-parses",
        {
            f"docs/decisions/{FILE_0001}": _adr_text("0001", broken_rev_keyword=True),
            f"docs/decisions/{FILE_0002}": _adr_text("0002", broken_rev_keyword=True),
            "CITATIONS.md": "no citations here\n",
        },
        ["no ADR declared a rev — the head format or this parser is wrong"],
    ),
    _Case(
        "the-prose-citation-spelling-drifted-so-none-is-recognised",
        {"CITATIONS.md": f"Link only: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"},
        ["no prose citation was judged"],
    ),
    _Case(
        "the-link-spelling-drifted-so-none-is-recognised",
        {"CITATIONS.md": f"Prose only: {_cite('0001', 1)}.\n"},
        ["no link citation was judged"],
    ),
    _Case(
        "an-adr-revved-with-one-citation-left-behind",
        {
            f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2),
            "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002)),
            "CITATIONS.md": (
                f"Prose citation: {_cite('0001', 1)}.\n\n"
                f"Link citation, left behind: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"
            ),
        },
        [f"pins {ADR} 0002 rev 1, current is rev 2"],
    ),
    _Case(
        "two-files-carrying-one-number-at-the-same-rev",
        {f"docs/decisions/0001-dup.md": _adr_text("0001")},
        ["both carry number 0001"],
    ),
    _Case(
        "two-files-carrying-one-number-at-different-revs",
        {f"docs/decisions/0001-dup.md": _adr_text("0001", rev=2)},
        ["both carry number 0001"],
    ),
    _Case(
        "an-adr-titling-itself-a-number-its-filename-does-not-carry",
        {f"docs/decisions/{FILE_0002}": _adr_text("0002", title_number="0009")},
        ["titles itself 0009, but its filename and every citation of it say 0002"],
    ),
    _Case(
        "a-title-number-of-the-wrong-digit-count",
        {f"docs/decisions/{FILE_0002}": _adr_text("0002").replace("# 0002", "# 002")},
        ["titles itself 002, but its filename and every citation of it say 0002"],
    ),
    _Case(
        "an-adr-with-no-title-line",
        {f"docs/decisions/{FILE_0002}": _adr_text("0002", no_title=True)},
        ["opens with no `# NNNN …` line"],
    ),
    _Case(
        "an-entry-named-outside-nnnn-lowercase-slug-md",
        {"docs/decisions/0003-MixedCase.md": _adr_text("0003")},
        ["is not named `NNNN-<lowercase-slug>.md`"],
    ),
    _Case(
        "an-untracked-file-anywhere-in-the-tree",
        {},
        ["untracked, so the citation scan cannot read it"],
        untracked={"NOTES.md": "scratch\n"},
    ),
]

MUST_PASS: list[_Case] = [
    _Case("the-tree-as-it-stands"),
    _Case(
        "an-adr-revved-with-everything-moved-with-it",
        {
            f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2),
            "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002)),
            "CITATIONS.md": (
                f"Prose citation: {_cite('0001', 1)}.\n\n"
                f"Link citation: {_link('0002', 2, f'docs/decisions/{FILE_0002}')}.\n"
            ),
        },
    ),
    _Case(
        "a-changelog-line-pinning-a-rev-that-is-not-current",
        {
            f"docs/decisions/{FILE_0001}": _adr_text("0001", rev=2),
            "docs/decisions/README.md": _index(_row("0001", 2, FILE_0001), _row("0002", 1, FILE_0002)),
            "CITATIONS.md": (
                f"Prose citation: {_cite('0001', 2)}.\n\n"
                f"Link citation: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"
            ),
            f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=1).replace(
                "first written (#1 ticket).",
                f"first written (#1 ticket), superseding {_cite('0001', 1)}.",
            ),
        },
    ),
    _Case(
        "a-title-spelled-with-a-hyphen-rather-than-an-em-dash",
        {f"docs/decisions/{FILE_0002}": _adr_text("0002").replace("— Decision", "- Decision")},
    ),
    _Case(
        "a-title-whose-text-differs-from-its-index-rows-decision-cell",
        {f"docs/decisions/{FILE_0002}": _adr_text("0002").replace("Decision", "Something else entirely")},
    ),
    _Case(
        "a-blank-line-before-the-title",
        {f"docs/decisions/{FILE_0001}": _adr_text("0001", blank_lead=True)},
    ),
    _Case(
        "a-utf-8-bom-before-the-title",
        {f"docs/decisions/{FILE_0001}": _adr_text("0001", bom=True)},
    ),
    _Case(
        "an-untracked-file-once-tracked",
        {"NOTES.md": "scratch\n"},
    ),
]


@pytest.mark.parametrize("case", MUST_FAIL, ids=lambda c: c.id)
def test_must_fail(
    case: _Case, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = _build(tmp_path, case.overrides, case.untracked, case.extra)
    result = _run_check(repo, monkeypatch, capsys)
    _assert_failed(result, case.reports)


@pytest.mark.parametrize("case", MUST_PASS, ids=lambda c: c.id)
def test_must_pass(
    case: _Case, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = _build(tmp_path, case.overrides, case.untracked, case.extra)
    result = _run_check(repo, monkeypatch, capsys)
    _assert_passed(result)


def test_a_changelog_entry_pinning_a_stale_rev_is_exempt_from_currency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The exemption drops staleness, not form: the pin still has to be canonical and still has to
    carry a rev."""
    repo = _build(
        tmp_path,
        {
            f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2)
            + f"\n  a continuation pinning the superseded {_cite('0001', 1)}\n"
        },
    )
    result = _run_check(repo, monkeypatch, capsys)
    assert result.returncode != 0, result.stdout  # the rev-2 move above is incomplete on its own;
    # this test only pins that a changelog pin of the un-revved ADR this appends is not itself
    # flagged as stale.
    assert f"pins {_cite('0001')}" not in result.stderr


def test_a_directory_or_dangling_symlink_named_like_an_adr_is_not_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = _build(tmp_path, {})
    (repo / "docs/decisions/0003-notreal.md").mkdir()
    (repo / "docs/decisions/0003-notreal.md/inside.txt").write_text("x\n", encoding="utf-8")
    result = _run_check(repo, monkeypatch, capsys)
    assert result.returncode == 1
    assert "docs/decisions/0003-notreal.md is not a readable file" in result.stderr


def test_a_tracked_dangling_symlink_fails_on_the_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = _build(tmp_path, {})
    link = repo / "ghost-link.md"
    link.symlink_to(repo / "does-not-exist.md")
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "dangling symlink")
    assert commit.returncode == 0, commit.stderr

    result = _run_check(repo, monkeypatch, capsys)
    assert result.returncode == 1
    assert "ghost-link.md:" in result.stderr


def test_a_tracked_binary_file_is_reported_as_not_scanned_but_does_not_fail_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = _build(tmp_path, {})
    (repo / "binary.md").write_bytes(b"\xff\xfe\x00\x01")
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "binary file")
    assert commit.returncode == 0, commit.stderr

    result = _run_check(repo, monkeypatch, capsys)
    assert result.returncode == 0, result.stderr
    assert "not scanned, not decodable as text: binary.md" in result.stderr


def test_a_citation_of_a_colliding_number_is_left_unjudged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A citation of a colliding number is left unjudged, and the run fails on the collision
    itself, not a manufactured rev disagreement."""
    repo = _build(
        tmp_path,
        {
            "docs/decisions/0001-dup.md": _adr_text("0001"),
            "CITATIONS.md": f"Prose citation: {_cite('0001', 1)}.\n",
        },
    )
    result = _run_check(repo, monkeypatch, capsys)
    assert result.returncode == 1
    assert "both carry number 0001" in result.stderr
    assert f"pins {_cite('0001')}" not in result.stderr


def test_an_adr_carrying_no_index_row_is_still_judged_for_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = _build(
        tmp_path,
        {
            "docs/decisions/README.md": _index(_row("0002", 1, FILE_0002)),
            "CITATIONS.md": f"Prose citation: {_cite('0001', 1)}.\n\nLink: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n",
        },
    )
    result = _run_check(repo, monkeypatch, capsys)
    assert result.returncode == 1
    assert f"{_cite('0001', 1)} has no row in docs/decisions/README.md" in result.stderr


def test_index_rev_cell_not_a_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = _build(
        tmp_path,
        {"docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", "N/A", FILE_0002))},
    )
    result = _run_check(repo, monkeypatch, capsys)
    assert result.returncode == 1
    assert "has rev cell 'N/A', not a number" in result.stderr


def test_outside_a_repository_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """In-process: the uncaught CalledProcessError tracked()/untracked() raise when git itself
    fails (no repository) is asserted directly with pytest.raises, rather than read back from a
    subprocess's stderr traceback text."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(plain)
    # independent confirmation: the same git invocation the script makes, run directly.
    probe = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=plain, capture_output=True, text=True,
    )
    assert probe.returncode != 0

    with pytest.raises(subprocess.CalledProcessError):
        check_adr_revs.main()
