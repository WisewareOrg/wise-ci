"""Specifies check-eol/check-eol.py against WiseKiosk's scripts/cases/check-eol-py.md (ref 1becdf0)
-- a seed of cases, not an exhaustive list (docs/TESTING.md "Every case is a test") -- plus the
forced-CRLF-blob and binary-attribute-gap claims stated in that case file's prose, and the
GITHUB_ACTIONS annotation pair.

Each case builds a real, isolated git repository in a temporary directory and runs the real script
against it as a subprocess (docs/TESTING.md "Real dependencies where possible"). Nothing defective is
committed to this repository; every defective input is created on the fly.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-eol.py"

UNTRACKED_MSG = "untracked, so this check cannot search them — git add or gitignore each."
CRLF_PLAIN = "CRLF found in the files above; the repo is LF-only (.gitattributes)."
CRLF_ANNOTATED = "::error::CRLF line endings found in the files above; the repo is LF-only (.gitattributes)."
CLEAN_MSG = "No CRLF line endings in the tracked tree; no untracked file left unsearched."

# Shuts out the machine's own git configuration, so a case gives the same result on any machine and
# in CI (docs/TESTING.md "Real dependencies where possible").
_ISOLATION = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}
# A runner carries no identity; a fixture commit needs one to commit at all.
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-eol tests",
    "GIT_AUTHOR_EMAIL": "check-eol-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-eol tests",
    "GIT_COMMITTER_EMAIL": "check-eol-tests@wise-ci.invalid",
}


def _env(**overrides: str) -> dict[str, str]:
    env = {**os.environ, **_ISOLATION, **_IDENTITY}
    env.pop("GITHUB_ACTIONS", None)  # a case sets this itself; the ambient run must not leak it in
    env.update(overrides)
    return env


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], env=_env(), capture_output=True, text=True)


def _show_bytes(repo: Path, relpath: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{relpath}"], env=_env(), capture_output=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _init_repo(repo: Path) -> Path:
    result = subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], env=_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return repo


def _commit(repo: Path, files: dict[str, bytes], *, attributes: str | None = None) -> None:
    if attributes is not None:
        (repo / ".gitattributes").write_bytes(attributes.encode())
    for relpath, content in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    add = _git(repo, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
    assert commit.returncode == 0, commit.stderr
    # independent confirmation (never trust the check under test to prove its own fixture): the
    # committed blob carries the exact bytes written, not something git's own filters rewrote.
    for relpath, content in files.items():
        assert _show_bytes(repo, relpath) == content


def _write_untracked(repo: Path, files: dict[str, bytes]) -> None:
    for relpath, content in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    # independent confirmation: git itself reports these paths as untracked.
    status = _git(repo, "status", "--porcelain").stdout
    for relpath in files:
        assert f"?? {relpath}" in status


def _run_check(repo: Path, *, github_actions: bool = False) -> subprocess.CompletedProcess:
    overrides = {"GITHUB_ACTIONS": "true"} if github_actions else {}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo,
        env=_env(**overrides),
        capture_output=True,
        text=True,
    )


def _no_traceback(result: subprocess.CompletedProcess) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


@dataclass(frozen=True)
class _Case:
    id: str
    build: Callable[[Path], Path]
    check: Callable[[subprocess.CompletedProcess], None]


def _must_fail(*, stderr_has: str, stdout_has: str = "") -> Callable[[subprocess.CompletedProcess], None]:
    def check(result: subprocess.CompletedProcess) -> None:
        assert result.returncode == 1
        if stdout_has:
            assert stdout_has in result.stdout
        assert stderr_has in result.stderr
        assert CLEAN_MSG not in result.stdout
        _no_traceback(result)

    return check


def _must_pass(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0
    assert CLEAN_MSG in result.stdout
    _no_traceback(result)


def _tracked(files: dict[str, bytes], *, attributes: str | None = None) -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        repo = _init_repo(tmp_path / "repo")
        _commit(repo, files, attributes=attributes)
        return repo

    return build


def _untracked(tracked: dict[str, bytes], untracked: dict[str, bytes]) -> Callable[[Path], Path]:
    def build(tmp_path: Path) -> Path:
        repo = _init_repo(tmp_path / "repo")
        if tracked:
            _commit(repo, tracked)
        _write_untracked(repo, untracked)
        return repo

    return build


def _empty_repo(tmp_path: Path) -> Path:
    return _init_repo(tmp_path / "repo")


CASES: list[_Case] = [
    _Case(
        "crlf-tracked-txt",
        _tracked({"file.txt": b"line one\r\nline two\r\n"}),
        _must_fail(stdout_has="file.txt", stderr_has=CRLF_PLAIN),
    ),
    _Case(
        "crlf-tracked-md",
        _tracked({"file.md": b"line one\r\nline two\r\n"}),
        _must_fail(stdout_has="file.md", stderr_has=CRLF_PLAIN),
    ),
    _Case(
        # After a commit, nothing is staged; this row is the same shape as crlf-tracked-txt on
        # purpose -- WiseKiosk records it to rule out staged-vs-committed state mattering.
        "crlf-committed-nothing-staged",
        _tracked({"committed.txt": b"line one\r\nline two\r\n"}),
        _must_fail(stdout_has="committed.txt", stderr_has=CRLF_PLAIN),
    ),
    _Case(
        "crlf-uniform",
        _tracked({"uniform.txt": b"line one\r\nline two\r\nline three\r\n"}),
        _must_fail(stdout_has="uniform.txt", stderr_has=CRLF_PLAIN),
    ),
    _Case(
        "untracked-crlf",
        _untracked({}, {"bad.txt": b"line one\r\nline two\r\n"}),
        _must_fail(stderr_has=UNTRACKED_MSG),
    ),
    _Case(
        "untracked-all-lf",
        _untracked({}, {"clean.txt": b"line one\nline two\n"}),
        _must_fail(stderr_has=UNTRACKED_MSG),
    ),
    _Case(
        "untracked-beside-tracked-crlf",
        _untracked({"tracked.txt": b"line one\r\nline two\r\n"}, {"loose.txt": b"other\n"}),
        _must_fail(stdout_has="tracked.txt", stderr_has=UNTRACKED_MSG),
    ),
    _Case("all-lf-tree", _tracked({"a.txt": b"line one\nline two\n"}), _must_pass),
    _Case("binary-file-with-cr", _tracked({"image.bin": b"\x00\x01\x02\r\x03"}), _must_pass),
    _Case(
        # The untracked-all-lf file above, now tracked: the untracked guard is silent and the
        # search itself judges it clean.
        "untracked-lf-once-tracked",
        _tracked({"clean.txt": b"line one\nline two\n"}),
        _must_pass,
    ),
    _Case("cr-mid-line", _tracked({"midline.txt": b"line\rmore text\n"}), _must_pass),
    _Case("empty-tracked-tree", _empty_repo, _must_pass),
    _Case(
        # Not a WiseKiosk row: every row there is a top-level file. This confirms the search
        # recurses -- the migration's own docstring claims "the whole tracked tree".
        "crlf-tracked-nested",
        _tracked({"subdir/nested/file.txt": b"line one\r\nline two\r\n"}),
        _must_fail(stdout_has="subdir/nested/file.txt", stderr_has=CRLF_PLAIN),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case_file_row(case: _Case, tmp_path: Path) -> None:
    repo = case.build(tmp_path)
    result = _run_check(repo)
    case.check(result)


def test_outside_a_repository_fails_with_gits_status(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    # independent confirmation: the same git invocation the script makes, run directly.
    probe = subprocess.run(
        ["git", "-C", str(plain), "ls-files", "--others", "--exclude-standard", "--", "."],
        env=_env(),
        capture_output=True,
        text=True,
    )
    assert probe.returncode != 0

    result = _run_check(plain)

    assert result.returncode == probe.returncode
    assert result.stdout == ""
    _no_traceback(result)


def test_multiple_tracked_crlf_files_are_all_reported(tmp_path: Path) -> None:
    """Not a WiseKiosk row: every row there seeds a single defect. `git grep -l` lists every
    matching file, not just the first -- a search that stopped at one match would still pass every
    other case here but would fail this one."""
    repo = _init_repo(tmp_path / "repo")
    _commit(repo, {"first.txt": b"a\r\n", "second.txt": b"b\r\n"})

    result = _run_check(repo)

    assert result.returncode == 1
    assert "first.txt" in result.stdout
    assert "second.txt" in result.stdout
    assert CRLF_PLAIN in result.stderr
    _no_traceback(result)


def test_git_grep_itself_failing_is_distinct_from_outside_a_repository(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    _commit(repo, {"a.txt": b"hello\n"})
    bad_config = _git(repo, "config", "grep.patternType", "bogus")
    assert bad_config.returncode == 0

    # independent confirmation: git ls-files still succeeds; git grep itself is what fails.
    ls_files = _git(repo, "ls-files", "--others", "--exclude-standard", "--", ".")
    assert ls_files.returncode == 0
    grep = _git(repo, "grep", "-lIP", r"\r$", "--", ".")
    assert grep.returncode not in (0, 1)

    result = _run_check(repo)

    assert result.returncode == grep.returncode
    assert UNTRACKED_MSG not in result.stderr
    assert CLEAN_MSG not in result.stdout
    _no_traceback(result)


@pytest.mark.parametrize(
    ("github_actions", "must_be_in", "must_be_absent_from"),
    [
        pytest.param(True, (CRLF_ANNOTATED, "stdout"), (CRLF_PLAIN, "stderr"), id="github-actions-set"),
        pytest.param(False, (CRLF_PLAIN, "stderr"), (CRLF_ANNOTATED, "stdout"), id="github-actions-unset"),
    ],
)
def test_github_actions_toggles_the_annotation(
    tmp_path: Path,
    github_actions: bool,
    must_be_in: tuple[str, str],
    must_be_absent_from: tuple[str, str],
) -> None:
    repo = _init_repo(tmp_path / "repo")
    _commit(repo, {"file.txt": b"line one\r\nline two\r\n"})

    result = _run_check(repo, github_actions=github_actions)

    assert result.returncode == 1
    present_text, present_stream = must_be_in
    assert present_text in getattr(result, present_stream)
    absent_text, absent_stream = must_be_absent_from
    assert absent_text not in getattr(result, absent_stream)
    _no_traceback(result)


def test_forced_crlf_blob_survives_a_fresh_checkout(tmp_path: Path) -> None:
    payload = b"line one\r\nline two\r\n"
    source = _init_repo(tmp_path / "source")
    # `* text=auto eol=lf` is what a forced blob bypasses: it is the normalisation a plain `git add`
    # would have applied, so committing this file the ordinary way could never demonstrate the claim.
    _commit(source, {}, attributes="* text=auto eol=lf\n")

    hash_object = subprocess.run(
        ["git", "-C", str(source), "hash-object", "-w", "--stdin"],
        input=payload,
        env=_env(),
        capture_output=True,
    )
    assert hash_object.returncode == 0, hash_object.stderr
    blob = hash_object.stdout.decode().strip()

    update_index = _git(source, "update-index", "--add", "--cacheinfo", f"100644,{blob},forced.txt")
    assert update_index.returncode == 0, update_index.stderr
    commit = _git(source, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "force")
    assert commit.returncode == 0, commit.stderr

    clone = tmp_path / "clone"
    clone_result = subprocess.run(
        ["git", "clone", "-q", str(source), str(clone)], env=_env(), capture_output=True, text=True
    )
    assert clone_result.returncode == 0, clone_result.stderr
    # independent confirmation: the freshly checked-out working tree still carries the forced CRLF
    # bytes -- git's own normalisation does not rewrite a blob that already contains CRLF.
    assert (clone / "forced.txt").read_bytes() == payload

    result = _run_check(clone)

    assert result.returncode == 1
    assert "forced.txt" in result.stdout
    assert CRLF_PLAIN in result.stderr
    _no_traceback(result)


def test_binary_attribute_gap_is_pinned_as_passing(tmp_path: Path) -> None:
    """check-eol/README.md's documented gap: a file whose .gitattributes sets the `binary` macro is
    exempt both from CRLF normalisation on add and from the grep search itself, so a genuinely
    CRLF-terminated file passes. Pinned here as the expected (if regrettable) outcome of that gap,
    not as a guard against it -- the owner ruled not to gate it (check-eol/README.md)."""
    payload = b"line one\r\nline two\r\n"
    repo = _init_repo(tmp_path / "repo")
    _commit(repo, {"secret.txt": payload}, attributes="secret.txt binary\n")

    result = _run_check(repo)

    _must_pass(result)


def test_bare_text_attribute_does_not_open_the_gap(tmp_path: Path) -> None:
    """The case file's own boundary on the gap above: "a plain `-text` does not do this; only the
    full `binary` macro" -- `-text` alone disables add-time normalisation but does not set `-diff`,
    so the grep search still treats the file as text and still catches the CRLF."""
    payload = b"line one\r\nline two\r\n"
    repo = _init_repo(tmp_path / "repo")
    _commit(repo, {"secret.txt": payload}, attributes="secret.txt -text\n")

    result = _run_check(repo)

    assert result.returncode == 1
    assert "secret.txt" in result.stdout
    assert CRLF_PLAIN in result.stderr
    _no_traceback(result)
