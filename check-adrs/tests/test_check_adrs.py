"""Specifies check-adrs: check_adr_index -- the decisions directory and its index table agree --
check_adr_revs -- every citation of an ADR pins that ADR's current rev -- and the dispatcher that
runs every stage and exits 1 if either found a problem (check-adrs/README.md).

Every case runs the installed `check-adrs` console script as a subprocess, against a real git
repository built fresh in a temporary directory (docs/TESTING.md "Real dependencies where
possible"), the same pattern check-eol/tests/test_check_eol.py uses. The two stages run inside one
process, not two isolated ones, so a fixture exercising one stage's reporting paths must also leave
the other stage clean -- both check_adr_revs's own untracked-file guard and its rule that every
entry in docs/decisions/ must be an ADR, the index, or the template apply to every fixture here,
check_adr_index-only cases included. `BASE_FILES` is built to satisfy both stages at once, and
every override below is checked against both.

Two of the original check_adr_index-only cases cannot be transplanted whole: an uppercase `.MD`
extension and a stray non-ADR file/subdirectory in docs/decisions/ are both invisible to
check_adr_index but are both rejected outright by check_adr_revs's stricter "every entry is an ADR,
the index, or the template" rule. Those two keep their original assertion -- check_adr_index's own
pass message still appears in stdout -- but the process exits 1 overall, because check_adr_revs
independently, and correctly, rejects the same stray entry. See
test_an_uppercase_extension_is_invisible_to_check_adr_index_but_rejected_by_check_adr_revs and
test_a_stray_non_adr_entry_is_invisible_to_check_adr_index_but_rejected_by_check_adr_revs below.

No case spells a live citation (`ADR` followed by digits) as a literal string: every one is built at
runtime from separate parts, so this file's own text never reads as a citation when wise-ci's
check-adrs gates wise-ci's own tree.

A missing `docs/decisions/` is the empty ADR set: every citation still fails "not an ADR" rather
than going unjudged, and the zero-count and collision guards that would otherwise misreport that
as a parser fault are specific to an absent directory -- a present one holding only its own README
still behaves exactly as before. A citation wrapped across a line break right after `ADR` is
reported malformed on the ADR line, whatever comes next: missing, present, blockquote-continued,
indented, or (a documented false positive) a year.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

SCRIPT = Path(sys.executable).with_name("check-adrs")

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
    # inside the Revisions section -- an indented line continues it, an unindented one does not.
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

# Satisfies both stages at once: two contiguous, fully-indexed, revs-consistent ADRs, with one
# prose and one link citation, both current. Every case below overlays this.
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

STAGES = ("check_adr_index", "check_adr_revs")

INDEX_FAILED = "check-adr-index: the decisions directory and its index disagree"
INDEX_PASSED = "and its index agree:"
REVS_FAILED_HEADER = "problem(s):"
REVS_PASSED = "every one pinning the current rev"

_FAIL_HEADER = {"check_adr_index": INDEX_FAILED, "check_adr_revs": REVS_FAILED_HEADER}
_PASSED = {"check_adr_index": INDEX_PASSED, "check_adr_revs": REVS_PASSED}

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


def _build(
    tmp_path: Path,
    overrides: dict[str, str | None] | None = None,
    untracked: dict[str, str] | None = None,
    extra: Callable[[Path], None] | None = None,
) -> Path:
    """BASE_FILES overlaid with `overrides` (a None value drops that base file), committed into a
    fresh git repository. `extra` runs after writing the overlay but before `git add`, for a
    fixture Path operations (a directory, a symlink, raw bytes) can't express as text content.
    `untracked` is written after the commit, so it stays untracked."""
    repo = tmp_path / "repo"
    init = subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], env=_env(), capture_output=True, text=True
    )
    assert init.returncode == 0, init.stderr
    files = {**BASE_FILES, **(overrides or {})}
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


def _run_check(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT)], cwd=repo, env=_env(), capture_output=True, text=True)


def _fixture(
    overrides: dict[str, str | None] | None = None,
    untracked: dict[str, str] | None = None,
    extra: Callable[[Path], None] | None = None,
) -> Callable[[Path], Path]:
    """The check-reqs `_seed` pattern, over `_build` rather than `minimal_tree.build`."""

    def build(tmp_path: Path) -> Path:
        return _build(tmp_path, overrides, untracked, extra)

    return build


def _stage_header(stage: str) -> str:
    return f"check-adrs: {stage}"


def _no_traceback(result: subprocess.CompletedProcess) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def _must_fail_at(stage: str, *, has: str | tuple = ()) -> Callable:
    assert stage in STAGES
    needles = (has,) if isinstance(has, str) else has

    def check(result: subprocess.CompletedProcess) -> None:
        assert result.returncode != 0, result.stdout
        combined = result.stdout + result.stderr
        for s in STAGES:
            assert _stage_header(s) in result.stdout
        assert _FAIL_HEADER[stage] in result.stderr
        assert _PASSED[stage] not in result.stdout
        for needle in needles:
            assert needle in combined
        _no_traceback(result)

    return check


def _must_pass(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    for s in STAGES:
        assert _stage_header(s) in result.stdout
    for marker in _PASSED.values():
        assert marker in result.stdout
    _no_traceback(result)


@dataclass(frozen=True)
class _Case:
    id: str
    build: Callable[[Path], Path]
    check: Callable[[subprocess.CompletedProcess], None]


CASES: list[_Case] = [
    # check_adr_index
    _Case(
        "adr-file-with-no-row",
        _fixture({"docs/decisions/0003-gamma.md": "# 0003 — Gamma\n"}),
        _must_fail_at(
            "check_adr_index", has="docs/decisions/0003-gamma.md has no row in docs/decisions/README.md"
        ),
    ),
    _Case(
        "row-naming-no-file",
        _fixture(
            {
                "docs/decisions/README.md": _index(
                    _row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002), _row("0003", 1, "0003-ghost.md")
                )
            }
        ),
        _must_fail_at("check_adr_index", has="docs/decisions/README.md row 0003 names no ADR file"),
    ),
    _Case(
        "row-linking-the-wrong-filename",
        _fixture({f"docs/decisions/{FILE_0002}": None, "docs/decisions/0002-renamed.md": "# 0002 — Beta\n"}),
        _must_fail_at(
            "check_adr_index",
            has=f"docs/decisions/README.md row 0002 links '{FILE_0002}', but the file is '0002-renamed.md'",
        ),
    ),
    _Case(
        "two-files-carrying-one-number",
        _fixture({"docs/decisions/0002-dup.md": "# 0002 — Dup\n"}),
        _must_fail_at("check_adr_index", has=f"number 0002 is carried by two files: {FILE_0002}, 0002-dup.md"),
    ),
    _Case(
        "two-rows-for-one-number",
        _fixture(
            {
                "docs/decisions/README.md": _index(
                    _row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002), _row("0002", 1, FILE_0002)
                )
            }
        ),
        _must_fail_at("check_adr_index", has="docs/decisions/README.md has two rows for number 0002"),
    ),
    _Case(
        "numbering-not-contiguous-from-0001",
        _fixture(
            {
                f"docs/decisions/{FILE_0001}": None,
                "docs/decisions/0000-alpha.md": "# 0000 — Alpha\n",
                "docs/decisions/README.md": _index(_row("0000", 1, "0000-alpha.md"), _row("0002", 1, FILE_0002)),
            }
        ),
        _must_fail_at(
            "check_adr_index", has="ADR numbering is not contiguous from 0001: expected 0001, found 0000"
        ),
    ),
    _Case(
        "file-not-named-nnnn-slug-md",
        _fixture(
            {
                "docs/decisions/notes.md": "# Notes\n",
                "docs/decisions/00010-x.md": "# x\n",
            }
        ),
        _must_fail_at(
            "check_adr_index",
            has=(
                "docs/decisions/notes.md is not named NNNN-<slug>.md",
                "docs/decisions/00010-x.md is not named NNNN-<slug>.md",
            ),
        ),
    ),
    _Case(
        "a-directory-named-like-an-adr",
        _fixture(
            extra=lambda repo: (
                (repo / "docs/decisions/0003-notreal.md").mkdir(),
                (repo / "docs/decisions/0003-notreal.md/inside.txt").write_text("x\n"),
            )
        ),
        _must_fail_at("check_adr_index", has="docs/decisions/0003-notreal.md is not a readable file"),
    ),
    _Case(
        "a-dangling-symlink-named-like-an-adr",
        _fixture(
            extra=lambda repo: (repo / "docs/decisions/0004-ghost.md").symlink_to(
                repo / "docs/decisions/0004-nonexistent.md"
            )
        ),
        _must_fail_at("check_adr_index", has="docs/decisions/0004-ghost.md is not a readable file"),
    ),
    _Case("the-index-as-it-stands", _fixture(), _must_pass),
    _Case(
        "a-new-adr-plus-its-row",
        _fixture(
            {
                "docs/decisions/0003-gamma.md": _adr_text("0003"),
                "docs/decisions/README.md": _index(
                    _row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002), _row("0003", 1, "0003-gamma.md")
                ),
            }
        ),
        _must_pass,
    ),
    _Case("template-and-readme-skipped-by-name", _fixture(), _must_pass),
    _Case(
        "row-target-titled",
        _fixture(
            {
                "docs/decisions/README.md": _index(
                    f'| [0001]({FILE_0001} "Alpha") | 1 | 2026-01-01 | Decision 0001 |\n',
                    _row("0002", 1, FILE_0002),
                )
            }
        ),
        _must_pass,
    ),
    _Case(
        "row-target-angle-bracketed",
        _fixture(
            {
                "docs/decisions/README.md": _index(
                    f"| [0001](<{FILE_0001}>) | 1 | 2026-01-01 | Decision 0001 |\n", _row("0002", 1, FILE_0002)
                )
            }
        ),
        _must_pass,
    ),
    _Case(
        "row-target-leading-dot-slash",
        _fixture(
            {
                "docs/decisions/README.md": _index(
                    f"| [0001](./{FILE_0001}) | 1 | 2026-01-01 | Decision 0001 |\n", _row("0002", 1, FILE_0002)
                )
            }
        ),
        _must_pass,
    ),
    _Case(
        "row-target-with-anchor",
        _fixture(
            {
                "docs/decisions/README.md": _index(
                    f"| [0001]({FILE_0001}#context) | 1 | 2026-01-01 | Decision 0001 |\n",
                    _row("0002", 1, FILE_0002),
                )
            }
        ),
        _must_pass,
    ),
    _Case(
        # A target with a non-.md extension, unlike the index test's original "0009-nope.md": once
        # this runs through the full script, check_adr_revs would otherwise read the same
        # link-shaped text and judge it as an untitled link to an ADR file. The indentation point
        # under test -- the row regex is anchored to line start -- does not depend on the target's
        # extension.
        "a-4-space-indented-example-row",
        _fixture(
            {
                "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002))
                + "    "
                + _row("0009", 1, "0009-nope.txt")
            }
        ),
        _must_pass,
    ),
    _Case(
        # Same non-.md-extension adjustment as above, for the same reason: this file lives outside
        # docs/decisions/ entirely, so check_adr_index never reads it, but check_adr_revs scans
        # every tracked file for citations and would otherwise flag the row-shaped link.
        "a-row-in-a-markdown-file-outside-decisions",
        _fixture({"docs/OTHER.md": _row("0009", 1, "0009-nope.txt")}),
        _must_pass,
    ),
    # check_adr_revs
    _Case(
        "prose-citation-with-no-rev",
        _fixture({"CITATIONS.md": f"Prose citation: {_cite('0001')}.\n"}),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0001 without a rev"),
    ),
    _Case(
        "prose-citation-pinning-a-stale-rev",
        _fixture({"CITATIONS.md": f"Prose citation: {_cite('0001', 2)}.\n"}),
        _must_fail_at("check_adr_revs", has=f"pins {ADR} 0001 rev 2, current is rev 1"),
    ),
    _Case(
        "link-titled-with-a-bare-number",
        _fixture({"CITATIONS.md": f"Link: [{_cite('0002')}](docs/decisions/{FILE_0002}).\n"}),
        _must_fail_at("check_adr_revs", has=f"is titled '{ADR} 0002', expected `{ADR} 0002 rev N`"),
    ),
    _Case(
        "link-title-naming-a-different-adr-than-it-targets",
        _fixture({"CITATIONS.md": f"Link: {_link('0001', 1, f'docs/decisions/{FILE_0002}')}.\n"}),
        _must_fail_at("check_adr_revs", has=f"link titled {ADR} 0001 targets {FILE_0002}"),
    ),
    _Case(
        "ordinary-prose-inside-a-revisions-section",
        _fixture(
            {
                f"docs/decisions/{FILE_0001}": _adr_text(
                    "0001",
                    continuation=f"An ordinary sentence citing {_cite('0002')} without a rev.",
                )
            }
        ),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0002 without a rev"),
    ),
    _Case(
        "indented-continuation-of-ordinary-prose",
        _fixture(
            {
                f"docs/decisions/{FILE_0001}": _adr_text(
                    "0001",
                    continuation=f"  continued, citing {_cite('0002')} without a rev",
                )
            }
        ),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0002 without a rev"),
    ),
    _Case(
        "changelog-continuation-naming-a-number-no-adr-carries",
        _fixture(
            {
                f"docs/decisions/{FILE_0001}": _adr_text(
                    "0001",
                    continuation=f"  a continuation pinning {_cite('0009', 1)}, which does not exist",
                )
            }
        ),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0009, which is not an {ADR}"),
    ),
    _Case(
        "unpinned-citation-beside-a-correctly-titled-link",
        _fixture({"CITATIONS.md": f"See {_cite('0001')} and {_link('0001', 1, f'docs/decisions/{FILE_0001}')}.\n"}),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0001 without a rev"),
    ),
    _Case(
        "a-stale-citation-in-an-index-rows-decision-cell",
        _fixture(
            {
                "docs/decisions/README.md": _index(
                    _row("0001", 1, FILE_0001),
                    f"| [0002]({FILE_0002}) | 1 | 2026-01-01 | superseded by {_cite('0001', 2)} |\n",
                )
            }
        ),
        _must_fail_at("check_adr_revs", has=f"pins {ADR} 0001 rev 2, current is rev 1"),
    ),
    _Case(
        "index-rev-column-disagreeing-with-the-adrs-head",
        _fixture({"docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002))}),
        _must_fail_at("check_adr_revs", has="docs/decisions/README.md row 0002 says rev 2, its head says rev 1"),
    ),
    _Case(
        "adr-head-with-no-rev-line",
        _fixture({f"docs/decisions/{FILE_0001}": _adr_text("0001", no_rev_line=True)}),
        _must_fail_at("check_adr_revs", has="declares 0 `**Rev:** N` lines, expected 1"),
    ),
    _Case(
        "adr-revved-with-no-changelog-line-for-the-new-rev",
        _fixture(
            {
                f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2, changelog=[1]),
                "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002)),
                "CITATIONS.md": (
                    f"Prose citation: {_cite('0001', 1)}.\n\n"
                    f"Link citation: {_link('0002', 2, f'docs/decisions/{FILE_0002}')}.\n"
                ),
            }
        ),
        _must_fail_at(
            "check_adr_revs",
            has="is at rev 2 but its Revisions section declares [1], expected one line per rev from 1",
        ),
    ),
    _Case(
        "citation-of-a-number-no-adr-carries",
        _fixture({"CITATIONS.md": f"Prose citation: {_cite('0001', 1)}.\n\nAlso {_cite('0009', 1)}.\n"}),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0009, which is not an {ADR}"),
    ),
    _Case(
        "a-plural-a-hyphen-and-the-wrong-case",
        _fixture({"CITATIONS.md": f"{ADR}s-0001 rev 1, and {ADR.lower()} 0001 rev 1.\n"}),
        _must_fail_at("check_adr_revs", has=f"is not a citation this can pin — write `{ADR} 0001 rev N`"),
    ),
    _Case(
        "an-underscore-a-hash-a-doubled-space-and-too-few-digits",
        _fixture({"CITATIONS.md": f"{ADR}_0001 rev 1, {ADR}#0001 rev 1, {ADR}  0001 rev 1, {ADR} 1 rev 1.\n"}),
        _must_fail_at("check_adr_revs", has=f"is not a citation this can pin — write `{ADR} 0001 rev N`"),
    ),
    _Case(
        "a-reference-style-link-and-a-raw-a-href",
        _fixture(
            {
                "CITATIONS.md": (
                    f"[ref]: docs/decisions/{FILE_0001}\n\n"
                    f"Reference: [{_cite('0001', 1)}][ref].\n\n"
                    f'Raw: <a href="docs/decisions/{FILE_0002}">{_cite("0002", 1)}</a>.\n'
                )
            }
        ),
        _must_fail_at(
            "check_adr_revs",
            has=(
                f"cites an {ADR} as a reference-style link, which carries no rev",
                f"cites an {ADR} as a raw <a href>, which carries no rev",
            ),
        ),
    ),
    _Case(
        "a-link-to-an-adr-whose-title-carries-brackets",
        _fixture({"CITATIONS.md": f"[{_cite('0001', 1)} (see [elsewhere])](docs/decisions/{FILE_0001}).\n"}),
        _must_fail_at("check_adr_revs", has=("is titled", "expected")),
    ),
    _Case(
        "a-link-to-an-adr-wrapped-across-two-lines",
        _fixture({"CITATIONS.md": f"See [{_cite('0001', 1)}\n](docs/decisions/{FILE_0001})\n"}),
        _must_fail_at("check_adr_revs", has="has no title this can read"),
    ),
    _Case(
        "the-head-format-changed-everywhere-so-nothing-parses",
        _fixture(
            {
                f"docs/decisions/{FILE_0001}": _adr_text("0001", broken_rev_keyword=True),
                f"docs/decisions/{FILE_0002}": _adr_text("0002", broken_rev_keyword=True),
                "CITATIONS.md": "no citations here\n",
            }
        ),
        _must_fail_at("check_adr_revs", has="no ADR declared a rev — the head format or this parser is wrong"),
    ),
    _Case(
        "the-prose-citation-spelling-drifted-so-none-is-recognised",
        _fixture({"CITATIONS.md": f"Link only: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"}),
        _must_fail_at("check_adr_revs", has="no prose citation was judged"),
    ),
    _Case(
        "the-link-spelling-drifted-so-none-is-recognised",
        _fixture({"CITATIONS.md": f"Prose only: {_cite('0001', 1)}.\n"}),
        _must_fail_at("check_adr_revs", has="no link citation was judged"),
    ),
    _Case(
        "an-adr-revved-with-one-citation-left-behind",
        _fixture(
            {
                f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2),
                "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002)),
                "CITATIONS.md": (
                    f"Prose citation: {_cite('0001', 1)}.\n\n"
                    f"Link citation, left behind: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"
                ),
            }
        ),
        _must_fail_at("check_adr_revs", has=f"pins {ADR} 0002 rev 1, current is rev 2"),
    ),
    _Case(
        "two-files-carrying-one-number-at-the-same-rev",
        _fixture({"docs/decisions/0001-dup.md": _adr_text("0001")}),
        _must_fail_at("check_adr_revs", has="both carry number 0001"),
    ),
    _Case(
        "two-files-carrying-one-number-at-different-revs",
        _fixture({"docs/decisions/0001-dup.md": _adr_text("0001", rev=2)}),
        _must_fail_at("check_adr_revs", has="both carry number 0001"),
    ),
    _Case(
        "an-adr-titling-itself-a-number-its-filename-does-not-carry",
        _fixture({f"docs/decisions/{FILE_0002}": _adr_text("0002", title_number="0009")}),
        _must_fail_at(
            "check_adr_revs", has="titles itself 0009, but its filename and every citation of it say 0002"
        ),
    ),
    _Case(
        "a-title-number-of-the-wrong-digit-count",
        _fixture({f"docs/decisions/{FILE_0002}": _adr_text("0002").replace("# 0002", "# 002")}),
        _must_fail_at(
            "check_adr_revs", has="titles itself 002, but its filename and every citation of it say 0002"
        ),
    ),
    _Case(
        "an-adr-with-no-title-line",
        _fixture({f"docs/decisions/{FILE_0002}": _adr_text("0002", no_title=True)}),
        _must_fail_at("check_adr_revs", has="opens with no `# NNNN …` line"),
    ),
    _Case(
        "an-entry-named-outside-nnnn-lowercase-slug-md",
        _fixture({"docs/decisions/0003-MixedCase.md": _adr_text("0003")}),
        _must_fail_at("check_adr_revs", has="is not named `NNNN-<lowercase-slug>.md`"),
    ),
    _Case(
        "an-untracked-file-anywhere-in-the-tree",
        _fixture(untracked={"NOTES.md": "scratch\n"}),
        _must_fail_at("check_adr_revs", has="untracked, so the citation scan cannot read it"),
    ),
    _Case("the-tree-as-it-stands", _fixture(), _must_pass),
    _Case(
        "an-adr-revved-with-everything-moved-with-it",
        _fixture(
            {
                f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2),
                "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 2, FILE_0002)),
                "CITATIONS.md": (
                    f"Prose citation: {_cite('0001', 1)}.\n\n"
                    f"Link citation: {_link('0002', 2, f'docs/decisions/{FILE_0002}')}.\n"
                ),
            }
        ),
        _must_pass,
    ),
    _Case(
        "a-changelog-line-pinning-a-rev-that-is-not-current",
        _fixture(
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
            }
        ),
        _must_pass,
    ),
    _Case(
        "a-title-spelled-with-a-hyphen-rather-than-an-em-dash",
        _fixture({f"docs/decisions/{FILE_0002}": _adr_text("0002").replace("— Decision", "- Decision")}),
        _must_pass,
    ),
    _Case(
        "a-title-whose-text-differs-from-its-index-rows-decision-cell",
        _fixture({f"docs/decisions/{FILE_0002}": _adr_text("0002").replace("Decision", "Something else entirely")}),
        _must_pass,
    ),
    _Case(
        "a-blank-line-before-the-title",
        _fixture({f"docs/decisions/{FILE_0001}": _adr_text("0001", blank_lead=True)}),
        _must_pass,
    ),
    _Case(
        "a-utf-8-bom-before-the-title",
        _fixture({f"docs/decisions/{FILE_0001}": _adr_text("0001", bom=True)}),
        _must_pass,
    ),
    _Case("an-untracked-file-once-tracked", _fixture({"NOTES.md": "scratch\n"}), _must_pass),
    # The ADR-tail wrap (matrix A6/F5): a line break, optionally with a trailing separator or a
    # blockquote marker opening the next line, sits between `ADR` and its number as readily as a
    # space does, and is reported with the same malformed template, on the ADR line.
    _Case(
        "a-wrap-with-the-number-missing-from-the-adr-line",
        _fixture({"WRAP.md": f"A note citing {ADR}\n0017 here.\n"}),
        _must_fail_at(
            "check_adr_revs",
            has=(
                "WRAP.md:1:",
                f"'{ADR}\\n0017' is not a citation this can pin — write `{ADR} 0017 rev N`",
            ),
        ),
    ),
    _Case(
        "a-wrap-with-a-trailing-hyphen",
        _fixture({"WRAP.md": f"A note citing {ADR}-\n0017 here.\n"}),
        _must_fail_at(
            "check_adr_revs",
            has=f"'{ADR}-\\n0017' is not a citation this can pin — write `{ADR} 0017 rev N`",
        ),
    ),
    _Case(
        "a-wrap-with-a-blockquote-continuation",
        _fixture({"WRAP.md": f"A note citing {ADR}\n> 0017 here.\n"}),
        _must_fail_at(
            "check_adr_revs",
            has=f"'{ADR}\\n> 0017' is not a citation this can pin — write `{ADR} 0017 rev N`",
        ),
    ),
    _Case(
        "a-wrap-with-the-number-indented-on-the-next-line",
        _fixture({"WRAP.md": f"A note citing {ADR}\n   0017 here.\n"}),
        _must_fail_at(
            "check_adr_revs", has=f"is not a citation this can pin — write `{ADR} 0017 rev N`"
        ),
    ),
    _Case(
        # The same wrap pattern cannot tell a missing number from a 4-digit year starting the next
        # line -- the script carries the same risk (check-adrs/README.md).
        "a-year-on-the-next-line-is-a-documented-false-positive",
        _fixture({"WRAP.md": f"A note:\n{ADR}\n2026 was eventful.\n"}),
        _must_fail_at(
            "check_adr_revs",
            has=f"'{ADR}\\n2026' is not a citation this can pin — write `{ADR} 2026 rev N`",
        ),
    ),
    _Case(
        "adrnnnn-with-no-separator-is-malformed",
        _fixture({"WRAP.md": f"{ADR}0001 is mentioned here.\n"}),
        _must_fail_at(
            "check_adr_revs", has=f"'{ADR}0001' is not a citation this can pin — write `{ADR} 0001 rev N`"
        ),
    ),
    _Case(
        # Plan item D: a wrap is malformed whether the number is missing (the cases above) or
        # exists -- 0001 is one of BASE_FILES' own current, correctly-revved ADRs, so this is the
        # case that tells joining the wrapped pair (and judging it normally) apart from reporting
        # every wrap malformed regardless of what follows. It is the latter.
        "a-wrap-whose-number-exists-is-still-malformed",
        _fixture({"WRAP.md": f"A note citing {ADR}\n0001 rev 1 here.\n"}),
        _must_fail_at(
            "check_adr_revs",
            has=(
                "WRAP.md:1:",
                f"'{ADR}\\n0001' is not a citation this can pin — write `{ADR} 0001 rev N`",
            ),
        ),
    ),
    _Case(
        # The must-pass partner: TAIL matches a line ending in `ADR`, but the next line opens with
        # prose, not a digit -- NEXT_LINE does not match, so wrapped_citations finds nothing to
        # report. Nothing else on either line forms a citation on its own.
        "a-line-ending-in-adr-followed-by-prose-passes",
        _fixture({"WRAP.md": f"A note citing {ADR}\nsomething else entirely, no numbers at all.\n"}),
        _must_pass,
    ),
    # A8: check_adr_revs blanks no fences (the documented Known-rejection) -- a citation of a
    # missing number inside a fenced block, outside docs/decisions/, is judged exactly like one in
    # ordinary prose, not hidden the way check-reqs' own fence rule would hide it.
    _Case(
        "a-fenced-citation-of-a-missing-number-still-fails",
        _fixture({"FENCED.md": f"```\nSee {_cite('0009', 1)} for context.\n```\n"}),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0009, which is not an {ADR}"),
    ),
    # A16: the word boundary. A leading word character right before `ADR` (no boundary to open
    # the citation), and a 5th digit right after the 4 the number group admits (no boundary to
    # close it), both mean CITATION never matches at all -- neither is a citation, so both pass.
    _Case(
        "word-boundary-both-forms-pass",
        _fixture({"WORDBOUNDARY.md": f"X{ADR} 0002 is just a word. {ADR} 00021 is also not a citation.\n"}),
        _must_pass,
    ),
    _Case(
        # check_adr_revs scans every tracked file, not only Markdown: a non-ADR, non-Markdown file
        # holding a missing-ADR citation is judged exactly like a Markdown one.
        "a-missing-adr-citation-in-an-item-yaml-field-fails",
        _fixture({"docs/requirements/srs/SRS001.yml": f"rationale: cites {_cite('0009', 1)}, which does not exist\n"}),
        _must_fail_at("check_adr_revs", has=f"cites {ADR} 0009, which is not an {ADR}"),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: _Case, tmp_path: Path) -> None:
    repo = case.build(tmp_path)
    result = _run_check(repo)
    case.check(result)


def test_an_untracked_adr_file_with_no_row_is_still_judged(tmp_path: Path) -> None:
    """check_adr_index's population is the directory, os.listdir reports it like any other entry --
    unlike check-docs-index, no untracked guard is needed for the index check itself
    (check-adrs/README.md). check_adr_revs independently guards on untracked files, so this fixture
    fails overall for two reasons; only check_adr_index's own report is pinned here."""
    repo = _build(tmp_path, {}, untracked={"docs/decisions/0003-untracked.md": "# 0003 — Untracked\n"})
    result = _run_check(repo)
    assert result.returncode == 1
    assert "docs/decisions/0003-untracked.md has no row in docs/decisions/README.md" in result.stderr


def test_fenced_code_block_row_is_read_as_a_real_row(tmp_path: Path) -> None:
    """Known rejection (check-adrs/README.md): there is no fence blanking, so an illustrative
    example table in docs/decisions/README.md is read like any other row. The fenced row sits in
    the index's own self-link column, which check_adr_revs's readable() always strips for
    docs/decisions/README.md regardless of fencing, so it stays clean here too."""
    repo = _build(
        tmp_path,
        {
            "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002))
            + "\n```\n"
            + _row("0009", 1, "0009-example.md")
            + "```\n"
        },
    )
    result = _run_check(repo)
    assert result.returncode == 1
    assert "docs/decisions/README.md row 0009 names no ADR file" in result.stderr


def test_an_uppercase_extension_is_invisible_to_check_adr_index_but_rejected_by_check_adr_revs(
    tmp_path: Path,
) -> None:
    """Known gap (check-adrs/README.md): check_adr_index's `name.endswith(".md")` is case-sensitive,
    so an ADR named with an uppercase extension is skipped rather than caught, and check_adr_index
    still reports no problem (its pass message appears below). check_adr_revs's own ADR-naming
    pattern is equally case-sensitive but carries no such exemption -- it reports any
    docs/decisions/ entry that is not README.md, TEMPLATE.md, or NNNN-<lowercase-slug>.md -- so the
    script exits 1 overall for a reason check_adr_index does not share. Both facts hold at once: this
    is not a case a shared fixture can make exit 0, since the two checks disagree by design on what
    docs/decisions/ may hold."""
    repo = _build(tmp_path, {})
    (repo / "docs/decisions/0003-upper.MD").write_text("# 0003 — Upper\n", encoding="utf-8")
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "uppercase extension")
    assert commit.returncode == 0, commit.stderr

    result = _run_check(repo)

    assert INDEX_PASSED in result.stdout
    assert result.returncode == 1
    assert "0003-upper.MD" in result.stderr


def test_a_stray_non_adr_entry_is_invisible_to_check_adr_index_but_rejected_by_check_adr_revs(
    tmp_path: Path,
) -> None:
    """check_adr_index's directory scan only looks at `.md`-named entries at all, so a non-.md file
    and a subdirectory in docs/decisions/ are both silently skipped and check_adr_index still
    reports no problem (its pass message appears below). check_adr_revs reports every
    docs/decisions/ entry that is not an ADR, the index, or the template as a problem, so the merged
    script exits 1 overall for a reason check_adr_index does not share -- the mirror of the
    uppercase-extension case above, and not fixable without changing what either check means."""
    repo = _build(tmp_path, {})
    (repo / "docs/decisions/notes.txt").write_text("scratch\n", encoding="utf-8")
    (repo / "docs/decisions/assets").mkdir()
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "stray entries")
    assert commit.returncode == 0, commit.stderr

    result = _run_check(repo)

    assert INDEX_PASSED in result.stdout
    assert result.returncode == 1
    assert "notes.txt" in result.stderr


def test_a_changelog_entry_pinning_a_stale_rev_is_exempt_from_currency(tmp_path: Path) -> None:
    """The exemption drops staleness, not form: the pin still has to be canonical and still has to
    carry a rev."""
    repo = _build(
        tmp_path,
        {
            f"docs/decisions/{FILE_0002}": _adr_text("0002", rev=2)
            + f"\n  a continuation pinning the superseded {_cite('0001', 1)}\n"
        },
    )
    result = _run_check(repo)
    assert result.returncode != 0, result.stdout  # the rev-2 move above is incomplete on its own;
    # this test only pins that a changelog pin of the un-revved ADR this appends is not itself
    # flagged as stale.
    assert f"pins {_cite('0001')}" not in result.stderr


def test_a_directory_or_dangling_symlink_named_like_an_adr_is_not_readable(tmp_path: Path) -> None:
    repo = _build(
        tmp_path,
        {},
        extra=lambda repo: (
            (repo / "docs/decisions/0003-notreal.md").mkdir(),
            (repo / "docs/decisions/0003-notreal.md/inside.txt").write_text("x\n"),
        ),
    )
    result = _run_check(repo)
    assert result.returncode == 1
    assert "docs/decisions/0003-notreal.md is not a readable file" in result.stderr


def test_a_tracked_dangling_symlink_fails_on_the_read(tmp_path: Path) -> None:
    repo = _build(
        tmp_path, {}, extra=lambda repo: (repo / "ghost-link.md").symlink_to(repo / "does-not-exist.md")
    )
    result = _run_check(repo)
    assert result.returncode == 1
    assert "ghost-link.md:" in result.stderr


def test_a_tracked_binary_file_is_reported_as_not_scanned_but_does_not_fail_alone(tmp_path: Path) -> None:
    repo = _build(tmp_path, {}, extra=lambda repo: (repo / "binary.md").write_bytes(b"\xff\xfe\x00\x01"))
    result = _run_check(repo)
    assert result.returncode == 0, result.stderr
    assert "not scanned, not decodable as text: binary.md" in result.stderr


def test_a_citation_of_a_colliding_number_is_left_unjudged(tmp_path: Path) -> None:
    """A citation of a colliding number is left unjudged, and the run fails on the collision
    itself, not a manufactured rev disagreement."""
    repo = _build(
        tmp_path,
        {
            "docs/decisions/0001-dup.md": _adr_text("0001"),
            "CITATIONS.md": f"Prose citation: {_cite('0001', 1)}.\n",
        },
    )
    result = _run_check(repo)
    assert result.returncode == 1
    assert "both carry number 0001" in result.stderr
    assert f"pins {_cite('0001')}" not in result.stderr


def test_an_adr_carrying_no_index_row_is_still_judged_for_citations(tmp_path: Path) -> None:
    repo = _build(
        tmp_path,
        {
            "docs/decisions/README.md": _index(_row("0002", 1, FILE_0002)),
            "CITATIONS.md": (
                f"Prose citation: {_cite('0001', 1)}.\n\n"
                f"Link: {_link('0002', 1, f'docs/decisions/{FILE_0002}')}.\n"
            ),
        },
    )
    result = _run_check(repo)
    assert result.returncode == 1
    assert f"{_cite('0001', 1)} has no row in docs/decisions/README.md" in result.stderr


def test_index_rev_cell_not_a_number(tmp_path: Path) -> None:
    repo = _build(
        tmp_path,
        {"docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", "N/A", FILE_0002))},
    )
    result = _run_check(repo)
    assert result.returncode == 1
    assert "has rev cell 'N/A', not a number" in result.stderr


def test_outside_a_repository_fails(tmp_path: Path) -> None:
    """The dispatcher isolates no stage from a crash: check_adr_index needs no git repository at
    all and still passes (its pass message and header appear below), but check_adr_revs's own
    `git ls-files` call then fails outright with no repository to search, and that
    CalledProcessError propagates straight out of the console script -- the same uncaught-exception
    traceback Python prints for any script left to crash on its own."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(
        repo,
        {
            "docs/decisions/README.md": _index(_row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002)),
            "docs/decisions/TEMPLATE.md": "# NNNN — Title\n",
            f"docs/decisions/{FILE_0001}": _adr_text("0001"),
            f"docs/decisions/{FILE_0002}": _adr_text("0002"),
        },
    )
    env = _env(GIT_CEILING_DIRECTORIES=str(tmp_path))
    # independent confirmation: the same git invocation check_adr_revs makes, run directly.
    probe = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo, env=env, capture_output=True, text=True
    )
    assert probe.returncode != 0

    result = subprocess.run([str(SCRIPT)], cwd=repo, env=env, capture_output=True, text=True)

    assert INDEX_PASSED in result.stdout
    for s in STAGES:
        assert _stage_header(s) in result.stdout
    assert result.returncode != 0
    assert "Traceback" in result.stderr
    assert "CalledProcessError" in result.stderr


def test_missing_decisions_folder_with_a_citation_fails_as_not_an_adr(tmp_path: Path) -> None:
    """docs/decisions/ absent is the empty ADR set: check_adr_index prints its existing 0-ADR
    success line, and the citation is still judged -- against zero ADRs -- rather than left
    unjudged the way a present-but-empty decisions/ leaves it (see the README-only case below)."""
    overrides = {
        "docs/decisions/README.md": None,
        "docs/decisions/TEMPLATE.md": None,
        f"docs/decisions/{FILE_0001}": None,
        f"docs/decisions/{FILE_0002}": None,
        "CITATIONS.md": f"Prose citation: {_cite('0001', 1)}.\n",
    }
    repo = _build(tmp_path, overrides)
    assert not (repo / "docs/decisions").exists()

    result = _run_check(repo)

    for s in STAGES:
        assert _stage_header(s) in result.stdout
    assert result.returncode == 1
    assert INDEX_PASSED in result.stdout
    assert "0 ADR(s), contiguous from 0001." in result.stdout
    assert f"cites {ADR} 0001, which is not an {ADR}" in result.stderr
    assert REVS_PASSED not in result.stdout


def test_missing_decisions_folder_with_no_citation_passes(tmp_path: Path) -> None:
    """Zero ADRs and zero citations is not the parser-fault zero-count guard firing, and not the
    'no ADR declared a rev' guard either -- it is the expected state of a repository that declares
    no ADRs at all."""
    overrides = {
        "docs/decisions/README.md": None,
        "docs/decisions/TEMPLATE.md": None,
        f"docs/decisions/{FILE_0001}": None,
        f"docs/decisions/{FILE_0002}": None,
        "CITATIONS.md": "No citations here.\n",
    }
    repo = _build(tmp_path, overrides)
    assert not (repo / "docs/decisions").exists()

    result = _run_check(repo)

    for s in STAGES:
        assert _stage_header(s) in result.stdout
    assert result.returncode == 0, result.stderr
    assert "0 ADR(s), contiguous from 0001." in result.stdout
    assert "0 ADRs; 0 citations, every one pinning the current rev" in result.stdout
    combined = result.stdout + result.stderr
    assert "no prose citation was judged" not in combined
    assert "no link citation was judged" not in combined
    assert "no ADR declared a rev" not in combined


def test_decisions_folder_present_with_no_readme_still_crashes(tmp_path: Path) -> None:
    """A present but README-less decisions/ is not the missing-folder case -- only an absent
    directory is the empty ADR set. Unchanged: FileNotFoundError, uncaught."""
    overrides = {
        "docs/decisions/README.md": None,
        "docs/decisions/TEMPLATE.md": None,
        f"docs/decisions/{FILE_0001}": None,
        f"docs/decisions/{FILE_0002}": None,
    }
    repo = _build(tmp_path, overrides, extra=lambda repo: (repo / "docs/decisions").mkdir(parents=True))
    assert (repo / "docs/decisions").is_dir()
    assert not (repo / "docs/decisions/README.md").exists()

    result = _run_check(repo)

    assert result.returncode != 0
    assert "Traceback" in result.stderr
    assert "FileNotFoundError" in result.stderr


def test_decisions_folder_with_only_a_readme_leaves_citations_unjudged(tmp_path: Path) -> None:
    """A present decisions/ holding only its own README is not the missing-folder case either: the
    zero-count and 'no ADR declared a rev' guards still fire, and a real citation present in the
    tree is still left unjudged, exactly as today."""
    overrides = {
        "docs/decisions/README.md": _index(),
        "docs/decisions/TEMPLATE.md": None,
        f"docs/decisions/{FILE_0001}": None,
        f"docs/decisions/{FILE_0002}": None,
        "CITATIONS.md": f"Prose citation: {_cite('0001', 1)}.\n",
    }
    repo = _build(tmp_path, overrides)

    result = _run_check(repo)

    assert result.returncode == 1
    assert INDEX_PASSED in result.stdout
    assert "0 ADR(s), contiguous from 0001." in result.stdout
    assert "no ADR declared a rev — the head format or this parser is wrong" in result.stderr
    assert f"cites {ADR} 0001, which is not an {ADR}" not in result.stderr


def test_independent_failures_in_both_stages_are_both_reported_in_one_run(tmp_path: Path) -> None:
    """Plan criterion 4, for check-adrs: both stages run unconditionally and OR their results
    (pre-existing, unchanged by this ticket), so a defect local to each -- an index row naming no
    file, and an unrelated citation elsewhere pinning no rev -- both surface in the one run rather
    than either masking the other."""
    repo = _build(
        tmp_path,
        {
            "docs/decisions/README.md": _index(
                _row("0001", 1, FILE_0001), _row("0002", 1, FILE_0002), _row("0003", 1, "0003-ghost.md")
            ),
            "STALE.md": f"Unrelated citation: {_cite('0001')}.\n",
        },
    )

    result = _run_check(repo)

    assert result.returncode != 0
    for s in STAGES:
        assert _stage_header(s) in result.stdout
    assert INDEX_PASSED not in result.stdout
    assert REVS_PASSED not in result.stdout
    assert "docs/decisions/README.md row 0003 names no ADR file" in result.stderr
    assert f"cites {ADR} 0001 without a rev" in result.stderr
    _no_traceback(result)
