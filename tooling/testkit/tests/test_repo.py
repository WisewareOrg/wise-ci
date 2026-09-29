"""Specifies testkit.repo.make_repo."""

import subprocess
from pathlib import Path

from testkit.repo import make_repo


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def test_make_repo_returns_a_git_repository(tmp_path):
    repo = make_repo(tmp_path, {"a.txt": b"hello\n"})
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "true"


def test_make_repo_default_branch_is_main(tmp_path):
    repo = make_repo(tmp_path, {"a.txt": b"hello\n"})
    result = _git(repo, "symbolic-ref", "HEAD")
    assert result.stdout.strip() == "refs/heads/main"


def test_make_repo_writes_file_bytes_exactly(tmp_path):
    payload = b"line one\r\nline two\r\n"
    repo = make_repo(tmp_path, {"crlf.txt": payload})
    assert (repo / "crlf.txt").read_bytes() == payload


def test_make_repo_commits_by_default(tmp_path):
    repo = make_repo(tmp_path, {"a.txt": b"hello\n"})
    log = _git(repo, "log", "--oneline")
    assert log.stdout.strip() != ""
    status = _git(repo, "status", "--porcelain")
    assert status.stdout == ""


def test_make_repo_commit_false_leaves_nothing_committed(tmp_path):
    repo = make_repo(tmp_path, {"a.txt": b"hello\n"}, commit=False)
    log = subprocess.run(
        ["git", "-C", str(repo), "log"],
        capture_output=True,
        text=True,
    )
    assert log.returncode != 0


def test_make_repo_attributes_written_verbatim(tmp_path):
    text = "* text=auto eol=lf\n"
    repo = make_repo(tmp_path, {"a.txt": b"hi\n"}, attributes=text)
    assert (repo / ".gitattributes").read_text() == text


def test_make_repo_identity_and_dates_are_fixed_across_calls(tmp_path):
    repo_a = make_repo(tmp_path / "a", {"a.txt": b"hi\n"})
    repo_b = make_repo(tmp_path / "b", {"a.txt": b"hi\n"})
    fmt = "--format=%an%x00%ae%x00%cn%x00%ce%x00%ad%x00%cd"
    show_a = _git(repo_a, "log", "-1", fmt, "--date=iso-strict")
    show_b = _git(repo_b, "log", "-1", fmt, "--date=iso-strict")
    assert show_a.stdout == show_b.stdout
