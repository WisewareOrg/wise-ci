"""Specifies check-docs-index/check-docs-index.py: every reporting path in both directions, the
untracked-file guard, the machinery line, git failing outright, and the legal Markdown the check
refuses (check-docs-index/README.md).

Each case builds a real, isolated git repository in a temporary directory, over a minimal fixture
index — three rows over `README.md`, `decisions/` and `architecture/` — rather than a copy of a real
documentation set, so a case states its own premise. The real script runs against it as a subprocess
(docs/TESTING.md "Real dependencies where possible"). Nothing defective is committed to this
repository; every defective input is created on the fly.
"""

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-docs-index.py"

INDEX = "docs/README.md"
HEADER = "| Document | Guarantees | Excludes |\n|---|---|---|\n"
ROW_README = "| [`../README.md`](../README.md) | What the fixture is | Everything else |\n"
ROW_DECISIONS = "| [`decisions/`](decisions/README.md) | The decisions | Everything else |\n"
ROW_ARCHITECTURE = "| [`architecture/`](architecture/README.md) | The architecture | Everything else |\n"
BASE_INDEX = "# Index\n\n" + HEADER + ROW_README + ROW_DECISIONS + ROW_ARCHITECTURE
BASE_FILES = {
    "README.md": "# Fixture\n",
    INDEX: BASE_INDEX,
    "docs/decisions/README.md": "# Decisions\n",
    "docs/architecture/README.md": "# Architecture\n",
}

FAILED = "check-docs-index: the documentation set and its index disagree"
PASSED = "every tracked document is claimed:"
MACHINERY = "machinery, claimed by nothing:"

# Shuts out the machine's own git configuration, so a case gives the same result on any machine and
# in CI (docs/TESTING.md "Real dependencies where possible").
_ISOLATION = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}
# A runner carries no identity; a fixture commit needs one to commit at all.
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-docs-index tests",
    "GIT_AUTHOR_EMAIL": "check-docs-index-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-docs-index tests",
    "GIT_COMMITTER_EMAIL": "check-docs-index-tests@wise-ci.invalid",
}


def _env(**overrides: str) -> dict[str, str]:
    # Every GIT_* variable is stripped first: GIT_DIR, GIT_WORK_TREE, GIT_CONFIG_COUNT/KEY_n/VALUE_n
    # and GIT_CONFIG_PARAMETERS all reach a fixture's git calls and the script otherwise, silently
    # redirecting commands onto an unrelated repository or injecting configuration no case set.
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
    tracked: dict[str, str | None],
    untracked: dict[str, str] | None = None,
) -> Path:
    """The base fixture overlaid with `tracked`, committed; a None value drops that base file."""
    repo = tmp_path / "repo"
    init = subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], env=_env(), capture_output=True, text=True
    )
    assert init.returncode == 0, init.stderr
    files = {**BASE_FILES, **tracked}
    committed = {path: content for path, content in files.items() if content is not None}
    _write(repo, committed)
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
    assert commit.returncode == 0, commit.stderr
    # independent confirmation (never trust the check under test to prove its own fixture): git
    # itself lists exactly the files this case meant to track.
    listed = set(_git(repo, "ls-files").stdout.split())
    assert listed == set(committed)

    if untracked:
        _write(repo, untracked)
        status = _git(repo, "status", "--porcelain", "--untracked-files=all").stdout
        for relpath in untracked:
            assert f"?? {relpath}" in status
    return repo


def _run_check(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=repo, env=_env(), capture_output=True, text=True
    )


@dataclass(frozen=True)
class _Case:
    id: str
    tracked: dict[str, str | None]
    reports: list[str] = field(default_factory=list)
    untracked: dict[str, str] = field(default_factory=dict)


def _index(*rows: str, preamble: str = "# Index\n\n") -> str:
    return preamble + HEADER + "".join(rows)


MUST_FAIL: list[_Case] = [
    _Case(
        "unindexed-document",
        {"docs/NEWDOC.md": "# New\n"},
        ["docs/NEWDOC.md has no row in docs/README.md"],
    ),
    _Case(
        "subtree-row-deleted-while-its-document-remains",
        {INDEX: _index(ROW_README, ROW_DECISIONS)},
        ["docs/architecture/README.md has no row in docs/README.md"],
    ),
    _Case(
        "row-links-an-untracked-file",
        {INDEX: _index(ROW_README, "| [`decisions/`](decisions/GONE.md) | g | e |\n", ROW_ARCHITECTURE)},
        ["docs/README.md: row 'decisions/' links 'decisions/GONE.md', which is not a tracked file"],
    ),
    _Case(
        "empty-guarantees-cell",
        {INDEX: _index(ROW_README, "| [`decisions/`](decisions/README.md) |  | e |\n", ROW_ARCHITECTURE)},
        ["docs/README.md: row 'decisions/' has an empty Guarantees cell"],
    ),
    _Case(
        "empty-excludes-cell",
        {INDEX: _index(ROW_README, "| [`decisions/`](decisions/README.md) | g |  |\n", ROW_ARCHITECTURE)},
        ["docs/README.md: row 'decisions/' has an empty Excludes cell"],
    ),
    _Case(
        # The parse matching nothing must not read as every document claimed by nothing and nothing
        # to report: the row count is asserted against the git population independently.
        "rows-reshaped-as-list-items",
        {
            INDEX: "# Index\n\n"
            "- [`../README.md`](../README.md) — g — e\n"
            "- [`decisions/`](decisions/README.md) — g — e\n"
            "- [`architecture/`](architecture/README.md) — g — e\n"
        },
        [
            "docs/README.md: no index row parsed — the table's shape has moved",
            "README.md has no row in docs/README.md",
        ],
    ),
    _Case(
        "two-rows-for-one-rendered-path",
        {INDEX: _index(ROW_README, ROW_DECISIONS, ROW_DECISIONS, ROW_ARCHITECTURE)},
        ["docs/README.md: 'decisions/' has two rows — one fact, one canonical home"],
    ),
    _Case(
        "file-row-names-no-tracked-document",
        {INDEX: BASE_INDEX + "| [`GHOST.md`](../README.md) | g | e |\n"},
        ["docs/README.md: row 'GHOST.md' names no tracked document"],
    ),
    _Case(
        "subtree-row-over-a-directory-holding-no-document",
        {INDEX: BASE_INDEX + "| [`ghost/`](../README.md) | g | e |\n"},
        ["docs/README.md: row 'ghost/' claims a directory holding no tracked document"],
    ),
    _Case(
        "row-indexes-a-dot-directory",
        {
            ".github/NOTES.md": "# Notes\n",
            INDEX: BASE_INDEX + "| [`../.github/NOTES.md`](../.github/NOTES.md) | g | e |\n",
        },
        ["docs/README.md: row '../.github/NOTES.md' indexes a dot-directory, which is machinery"],
    ),
    _Case(
        # A dot-*file* is not a dot-*directory*: only a path with a `/` after its leading dot is
        # machinery.
        "dot-file-at-the-root",
        {".HIDDEN.md": "# Hidden\n"},
        [".HIDDEN.md has no row in docs/README.md"],
    ),
    _Case(
        "untracked-document",
        {},
        ["docs/decisions/DRAFT.md: untracked, so this check cannot read it — git add or gitignore it"],
        untracked={"docs/decisions/DRAFT.md": "# Draft\n"},
    ),
    _Case(
        # The untracked guard is deliberately wider than the claims rule, which lets the same file
        # through once tracked (dot-directory-document, below).
        "untracked-document-under-a-dot-directory",
        {},
        [".github/DRAFT.md: untracked, so this check cannot read it — git add or gitignore it"],
        untracked={".github/DRAFT.md": "# Draft\n"},
    ),
    _Case(
        # The placeholder row a documentation index might carry for a family of files: a Document
        # cell that is not a link fails rather than claiming anything.
        "placeholder-row",
        {INDEX: BASE_INDEX + "| `<check>/README.md` | g | e |\n"},
        ["docs/README.md: Document cell '`<check>/README.md`' is not a backticked-path link"],
    ),
    _Case(
        # The index file itself is present but untracked, so the git population is empty while the
        # table still parses: the empty population is reported in its own right.
        "no-tracked-markdown",
        {path: None for path in BASE_FILES} | {"LICENSE": "fixture\n"},
        ["git ls-files reported no tracked Markdown file"],
        untracked={INDEX: _index("| [`decisions/`](decisions/) | g | e |\n")},
    ),
]

KNOWN_REJECTIONS: list[_Case] = [
    _Case(
        "gfm-alignment-delimiters",
        {INDEX: "# Index\n\n| Document | Guarantees | Excludes |\n|:---|:---|:---|\n"
         + ROW_README + ROW_DECISIONS + ROW_ARCHITECTURE},
        ["docs/README.md: Document cell ':---' is not a backticked-path link"],
    ),
    _Case(
        "a-second-table",
        {INDEX: BASE_INDEX + "\n| A | B |\n|---|---|\n| one | two |\n"},
        ["docs/README.md: a row has 2 cells, expected Document, Guarantees, Excludes"],
    ),
    _Case(
        # A code fence is not skipped: every `|`-leading line is read as an index row.
        "fenced-table-example",
        {INDEX: BASE_INDEX + "\n```\n| A | B |\n```\n"},
        ["docs/README.md: a row has 2 cells, expected Document, Guarantees, Excludes"],
    ),
    _Case(
        "table-indented-two-spaces",
        {INDEX: "# Index\n\n" + "".join("  " + line + "\n" for line in (HEADER + ROW_README + ROW_DECISIONS + ROW_ARCHITECTURE).splitlines())},
        ["docs/README.md: no index row parsed — the table's shape has moved"],
    ),
    _Case(
        "link-text-without-backticks",
        {INDEX: _index("| [../README.md](../README.md) | g | e |\n", ROW_DECISIONS, ROW_ARCHITECTURE)},
        ["docs/README.md: Document cell '[../README.md](../README.md)' is not a backticked-path link"],
    ),
    _Case(
        "escaped-pipe-in-a-cell",
        {INDEX: _index(ROW_README, "| [`decisions/`](decisions/README.md) | a \\| b | e |\n", ROW_ARCHITECTURE)},
        ["docs/README.md: a row has 4 cells, expected Document, Guarantees, Excludes"],
    ),
]

MUST_PASS: list[_Case] = [
    _Case("base-fixture", {}),
    _Case("new-document-under-a-subtree-row", {"docs/decisions/0001-first.md": "# 0001\n"}),
    _Case("second-document-under-a-subtree-row", {"docs/architecture/MODEL.md": "# Model\n"}),
    _Case("document-nested-two-levels-under-a-subtree-row", {"docs/decisions/a/b/DEEP.md": "# Deep\n"}),
    _Case(
        "file-row-whose-rendered-path-and-link-agree",
        {"docs/CI.md": "# CI\n", INDEX: BASE_INDEX + "| [`CI.md`](CI.md) | g | e |\n"},
    ),
    _Case("untracked-file-that-is-not-markdown", {}, untracked={"notes.txt": "scratch\n"}),
]


def _assert_failed(result: subprocess.CompletedProcess, reports: list[str]) -> None:
    assert result.returncode == 1
    assert FAILED in result.stderr
    for report in reports:
        assert report in result.stderr
    assert PASSED not in result.stdout


@pytest.mark.parametrize("case", MUST_FAIL, ids=lambda c: c.id)
def test_must_fail(case: _Case, tmp_path: Path) -> None:
    repo = _build(tmp_path, case.tracked, case.untracked)
    _assert_failed(_run_check(repo), case.reports)


@pytest.mark.parametrize("case", KNOWN_REJECTIONS, ids=lambda c: c.id)
def test_known_rejection_fails_closed(case: _Case, tmp_path: Path) -> None:
    """Legal Markdown the check refuses (check-docs-index/README.md § Known rejections): each fails
    rather than letting a defect through."""
    repo = _build(tmp_path, case.tracked, case.untracked)
    _assert_failed(_run_check(repo), case.reports)


@pytest.mark.parametrize("case", MUST_PASS, ids=lambda c: c.id)
def test_must_pass(case: _Case, tmp_path: Path) -> None:
    repo = _build(tmp_path, case.tracked, case.untracked)
    result = _run_check(repo)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert f"{MACHINERY} none" in result.stdout


def test_success_counts_rows_and_documents(tmp_path: Path) -> None:
    repo = _build(tmp_path, {})
    result = _run_check(repo)
    assert result.returncode == 0, result.stderr
    assert f"{PASSED} 3 index row(s), 4 document(s)." in result.stdout


def test_dot_directory_document_is_machinery_and_named(tmp_path: Path) -> None:
    repo = _build(tmp_path, {".github/pull_request_template.md": "# Template\n"})
    result = _run_check(repo)
    assert result.returncode == 0, result.stderr
    assert f"{MACHINERY} .github/" in result.stdout


def test_new_dot_directory_passes_and_is_named(tmp_path: Path) -> None:
    """The accepted trade (ADR 0002 rev 1): a new top-level dot-directory is machinery the moment it
    exists, with no edit anywhere, and the machinery line is what names it."""
    repo = _build(tmp_path, {".github/NOTES.md": "# Notes\n", ".notes/NOTES.md": "# Notes\n"})
    result = _run_check(repo)
    assert result.returncode == 0, result.stderr
    assert f"{MACHINERY} .github/ .notes/" in result.stdout


def test_every_problem_is_reported_in_one_run(tmp_path: Path) -> None:
    """Findings accumulate rather than short-circuiting, and the header counts them."""
    repo = _build(
        tmp_path,
        {"docs/NEWDOC.md": "# New\n", INDEX: BASE_INDEX + "| [`GHOST.md`](../README.md) | g | e |\n"},
        {"docs/DRAFT.md": "# Draft\n"},
    )
    result = _run_check(repo)
    _assert_failed(
        result,
        [
            f"{FAILED} (3):",
            "docs/DRAFT.md: untracked",
            "row 'GHOST.md' names no tracked document",
            "docs/NEWDOC.md has no row in docs/README.md",
        ],
    )


def test_outside_a_repository_fails(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    # GIT_CEILING_DIRECTORIES stops git's upward discovery at tmp_path: without it, a pytest
    # --basetemp placed inside a git work tree lets git discover that outer repo instead of
    # failing here, so the case would depend on where the temp dir happens to sit.
    env = _env(GIT_CEILING_DIRECTORIES=str(tmp_path))
    # independent confirmation: the same git invocation the script makes, run directly.
    probe = subprocess.run(
        ["git", "ls-files", "-z", "*.md"], cwd=plain, env=env, capture_output=True, text=True
    )
    assert probe.returncode != 0

    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=plain, env=env, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert PASSED not in result.stdout
