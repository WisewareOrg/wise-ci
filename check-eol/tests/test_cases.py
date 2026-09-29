"""Specifies check-eol/check-eol.py against every row of WiseKiosk's scripts/cases/check-eol-py.md
(plan #4 W3), plus two claims stated in the case file's own prose rather than its table -- the
forced-CRLF-blob claim and the binary-attribute gap -- and the added GITHUB_ACTIONS pair. Runs the
real script from its real path via testkit.run.run_script; never imports it (decision 3).
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from testkit.cases import Case, case_id
from testkit.git_isolation import GIT_ISOLATION
from testkit.repo import make_repo
from testkit.run import Result, run_script

SCRIPT = Path(__file__).resolve().parents[1] / "check-eol.py"

UNTRACKED_MSG = "untracked, so this check cannot search them — git add or gitignore each."
CRLF_PLAIN = "CRLF found in the files above; the repo is LF-only (.gitattributes)."
CRLF_ANNOTATED = "::error::CRLF line endings found in the files above; the repo is LF-only (.gitattributes)."
CLEAN_MSG = "No CRLF line endings in the tracked tree; no untracked file left unsearched."

# Every git call this file makes directly (not through testkit.repo.make_repo) is isolated the
# same way (D5): the shared GIT_CONFIG_GLOBAL/NOSYSTEM pair (also used by make_repo and
# run_script), plus a fixed identity for any commit -- this file's own. A host with e.g.
# core.autocrlf=true silently rewrites a fixture's own CRLF bytes on commit, which no assertion
# here catches by accident; this closes that off at the source rather than per fixture.
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-eol tests",
    "GIT_AUTHOR_EMAIL": "check-eol-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-eol tests",
    "GIT_COMMITTER_EMAIL": "check-eol-tests@wise-ci.invalid",
}


def _env() -> dict[str, str]:
    return {**os.environ, **GIT_ISOLATION, **_IDENTITY}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        env=_env(),
        capture_output=True,
        text=True,
        check=True,
    )


def _committed_bytes(repo: Path, relpath: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{relpath}"],
        env=_env(),
        capture_output=True,
        check=True,
    )
    return result.stdout


def _write_untracked(repo: Path, files: dict[str, bytes]) -> None:
    for relpath, content in files.items():
        path = repo / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


@dataclass(frozen=True)
class _Scenario:
    case: Case
    build: Callable[[Path], Path]
    check: Callable[[Result], None]
    env: dict[str, str] | None = None


def _assert_committed_verbatim(repo: Path, files: dict[str, bytes]) -> None:
    # independent confirmation (D5): the committed blob's own bytes, not the guard under test. A
    # host with core.autocrlf=true (or similar) silently rewrites what actually got committed;
    # this is what would catch that, rather than an assertion that happens to pass anyway because
    # git grep reads the working tree, not the index.
    for relpath, content in files.items():
        assert _committed_bytes(repo, relpath) == content


def _tracked_repo(files: dict[str, bytes], *, attributes: str | None = None) -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        repo = make_repo(tmp_path / "repo", files, attributes=attributes)
        _assert_committed_verbatim(repo, files)
        return repo

    return build


def _untracked_repo(tracked: dict[str, bytes], untracked: dict[str, bytes]) -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        repo = make_repo(tmp_path / "repo", tracked, commit=bool(tracked))
        if tracked:
            _assert_committed_verbatim(repo, tracked)
        _write_untracked(repo, untracked)
        # independent confirmation (D5): untracked-ness via git status, not the guard under test.
        status = _git(repo, "status", "--porcelain").stdout
        for relpath in untracked:
            assert f"?? {relpath}" in status
        return repo

    return build


def _outside_a_repository() -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        plain = tmp_path / "not-a-repo"
        plain.mkdir()
        return plain

    return build


def _empty_tracked_repo() -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        return make_repo(tmp_path / "repo", {}, commit=False)

    return build


def _grep_itself_fails() -> tuple[Callable[[Path], Path], Callable[[Result], None]]:
    # Distinct from outside-a-repository: the untracked check (git ls-files) succeeds here, so the
    # script reaches the search step at all, and it's the search's own subprocess -- not the
    # untracked one -- whose non-0/1 status is what's propagated (check-eol.py:61-63). A bad local
    # grep.patternType makes `git grep` itself fatal while leaving `git ls-files` unaffected.
    observed: dict[str, int] = {}

    def build(tmp_path: Path) -> Path:
        repo = make_repo(tmp_path / "repo", {"a.txt": b"hello\n"})
        _git(repo, "config", "grep.patternType", "bogus")
        # independent confirmation (D5): both git calls run directly, not through the check under
        # test, before trusting the fixture -- ls-files still succeeds; grep alone goes fatal.
        ls_files = _git(repo, "ls-files", "--others", "--exclude-standard", "--", ".")
        assert ls_files.returncode == 0
        grep = subprocess.run(
            ["git", "-C", str(repo), "grep", "-lIP", r"\r$", "--", "."],
            env=_env(),
            capture_output=True,
            text=True,
        )
        assert grep.returncode not in (0, 1)
        observed["status"] = grep.returncode
        return repo

    def check(result: Result) -> None:
        assert result.status == observed["status"]
        assert UNTRACKED_MSG not in result.stderr
        _no_traceback(result)

    return build, check


def _forced_crlf_blob() -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        payload = "line one\r\nline two\r\n"
        source = make_repo(tmp_path / "source", {}, attributes="* text=auto eol=lf\n")
        blob = subprocess.run(
            ["git", "-C", str(source), "hash-object", "-w", "--stdin"],
            input=payload,
            env=_env(),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        _git(source, "update-index", "--add", "--cacheinfo", f"100644,{blob},forced.txt")
        _git(source, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "force")
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(source), str(clone)], env=_env(), capture_output=True, text=True, check=True
        )
        # independent confirmation (D5): the clone's bytes, not the guard under test.
        assert (clone / "forced.txt").read_bytes() == payload.encode()
        return clone

    return build


def _binary_attribute_gap() -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        payload = b"line one\r\nline two\r\n"
        repo = make_repo(tmp_path / "repo", {"secret.txt": payload}, attributes="secret.txt binary\n")
        # independent confirmation (D5): the tracked bytes, not the guard under test.
        assert (repo / "secret.txt").read_bytes() == payload
        return repo

    return build


def _no_traceback(result: Result) -> None:
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def _must_fail(*, stderr_has: str, stdout_has: str = "") -> Callable[[Result], None]:
    def check(result: Result) -> None:
        assert result.status == 1
        if stdout_has:
            assert stdout_has in result.stdout
        assert stderr_has in result.stderr
        assert CLEAN_MSG not in result.stdout
        _no_traceback(result)

    return check


def _must_pass(result: Result) -> None:
    assert result.status == 0
    assert CLEAN_MSG in result.stdout
    _no_traceback(result)


def _outside_a_repository_check(result: Result) -> None:
    assert result.status == 128
    _no_traceback(result)


def _github_actions_set_check(result: Result) -> None:
    assert result.status == 1
    assert CRLF_ANNOTATED in result.stdout
    assert CRLF_PLAIN not in result.stderr
    _no_traceback(result)


def _github_actions_unset_check(result: Result) -> None:
    assert result.status == 1
    assert CRLF_PLAIN in result.stderr
    assert CRLF_ANNOTATED not in result.stdout
    _no_traceback(result)


def _forced_crlf_blob_check(result: Result) -> None:
    assert result.status == 1
    assert "forced.txt" in result.stdout
    assert CRLF_PLAIN in result.stderr
    _no_traceback(result)


_SEARCH_FAILS_BUILD, _SEARCH_FAILS_CHECK = _grep_itself_fails()

SCENARIOS: list[_Scenario] = [
    _Scenario(
        Case("crlf-tracked-txt", "a tracked file containing CRLF, in `.txt` and in `.md`", "must-fail"),
        _tracked_repo({"file.txt": b"line one\r\nline two\r\n"}),
        _must_fail(stdout_has="file.txt", stderr_has=CRLF_PLAIN),
    ),
    _Scenario(
        Case("crlf-tracked-md", "a tracked file containing CRLF, in `.txt` and in `.md`", "must-fail"),
        _tracked_repo({"file.md": b"line one\r\nline two\r\n"}),
        _must_fail(stdout_has="file.md", stderr_has=CRLF_PLAIN),
    ),
    _Scenario(
        Case(
            "crlf-committed-unstaged",
            "a committed CRLF file with nothing staged *(gap: `mixed-line-ending` is handed only "
            "the staged set, so the same state passed it)*",
            "must-fail",
        ),
        _tracked_repo({"committed.txt": b"line one\r\nline two\r\n"}),
        _must_fail(stdout_has="committed.txt", stderr_has=CRLF_PLAIN),
    ),
    _Scenario(
        Case(
            "crlf-uniform",
            "a uniformly-CRLF file *(gap: `mixed-line-ending` counts one ending kind as unmixed and "
            "passed the same file; it fails only a genuinely mixed one, which was seeded separately "
            "to prove it can fail)*",
            "must-fail",
        ),
        _tracked_repo({"uniform.txt": b"line one\r\nline two\r\nline three\r\n"}),
        _must_fail(stdout_has="uniform.txt", stderr_has=CRLF_PLAIN),
    ),
    _Scenario(
        Case(
            "outside-a-repository",
            "the search failing rather than finding nothing — run outside a repository, where git "
            "exits 128 and the status is propagated",
            "must-fail",
        ),
        _outside_a_repository(),
        _outside_a_repository_check,
    ),
    _Scenario(
        Case(
            "search-itself-fails",
            "the search subprocess itself failing after the untracked check already succeeded — a "
            "local grep.patternType misconfiguration makes git grep fatal without git ls-files "
            "being affected, distinct from running outside a repository (where the untracked check "
            "fails first and the search step is never reached)",
            "must-fail",
        ),
        _SEARCH_FAILS_BUILD,
        _SEARCH_FAILS_CHECK,
    ),
    _Scenario(
        Case(
            "untracked-crlf",
            "an untracked CRLF file — reported by the untracked guard as unsearchable, not judged "
            "by the search",
            "must-fail",
        ),
        _untracked_repo({}, {"bad.txt": b"line one\r\nline two\r\n"}),
        _must_fail(stderr_has=UNTRACKED_MSG),
    ),
    _Scenario(
        Case(
            "untracked-all-lf",
            "an untracked all-LF file — same guard: visibility, not content, is what fails",
            "must-fail",
        ),
        _untracked_repo({}, {"clean.txt": b"line one\nline two\n"}),
        _must_fail(stderr_has=UNTRACKED_MSG),
    ),
    _Scenario(
        Case(
            "untracked-beside-tracked-crlf",
            "an untracked file beside a tracked CRLF file — one run reports both: the guard "
            "accumulates alongside the search rather than short-circuiting it",
            "must-fail",
        ),
        _untracked_repo({"tracked.txt": b"line one\r\nline two\r\n"}, {"loose.txt": b"other\n"}),
        _must_fail(stdout_has="tracked.txt", stderr_has=UNTRACKED_MSG),
    ),
    _Scenario(
        Case("all-lf-tree", "an all-LF tree", "must-pass"),
        _tracked_repo({"a.txt": b"line one\nline two\n"}),
        _must_pass,
    ),
    _Scenario(
        Case("binary-file-with-cr", "a binary file containing CR — excluded by `-I`", "must-pass"),
        _tracked_repo({"image.bin": b"\x00\x01\x02\r\x03"}),
        _must_pass,
    ),
    _Scenario(
        Case(
            "untracked-lf-once-tracked",
            "the untracked all-LF file from above, once tracked — the guard is silent and the "
            "search judges it",
            "must-pass",
        ),
        _tracked_repo({"clean.txt": b"line one\nline two\n"}),
        _must_pass,
    ),
    _Scenario(
        Case("cr-mid-line", "CR appearing mid-line, where the line still ends in LF", "must-pass"),
        _tracked_repo({"midline.txt": b"line\rmore text\n"}),
        _must_pass,
    ),
    _Scenario(
        Case(
            "empty-tracked-tree",
            "a repository with no tracked file — the retired population guard, exercised to "
            "confirm the ruling's side, not to guard: ADR 0016 rev 11's owner ruling is that an "
            "empty scan may report success",
            "must-pass",
        ),
        _empty_tracked_repo(),
        _must_pass,
    ),
    _Scenario(
        Case("github-actions-set", "the tracked-CRLF case with GITHUB_ACTIONS set: annotated ::error:: output", "must-fail"),
        _tracked_repo({"file.txt": b"line one\r\nline two\r\n"}),
        _github_actions_set_check,
        env={"GITHUB_ACTIONS": "true"},
    ),
    _Scenario(
        Case("github-actions-unset", "the tracked-CRLF case with GITHUB_ACTIONS unset: plain stderr output", "must-fail"),
        _tracked_repo({"file.txt": b"line one\r\nline two\r\n"}),
        _github_actions_unset_check,
    ),
    _Scenario(
        Case(
            "forced-crlf-blob",
            "a CRLF blob forced into history via hash-object/update-index, bypassing the add-time "
            "filter, is still caught after a fresh checkout",
            "must-fail",
        ),
        _forced_crlf_blob(),
        _forced_crlf_blob_check,
    ),
    _Scenario(
        Case(
            "binary-attribute",
            "a file whose .gitattributes sets the binary attribute both exempts it from CRLF→LF "
            "normalisation when added and makes -I skip it during the grep, so genuinely "
            "CRLF-terminated text commits and survives a fresh clone unseen",
            "gap",
        ),
        _binary_attribute_gap(),
        _must_pass,
    ),
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: case_id(s.case))
def test_case_file_row(scenario: _Scenario, tmp_path: Path) -> None:
    repo = scenario.build(tmp_path)
    result = run_script(SCRIPT, repo, env=scenario.env)
    scenario.check(result)
