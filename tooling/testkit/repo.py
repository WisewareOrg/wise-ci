"""testkit.repo.make_repo: a hermetic git repository for guard and check tests (TESTING.md D5).
"""

import os
import subprocess
from pathlib import Path

from testkit.git_isolation import GIT_ISOLATION

_IDENTITY = {
    "GIT_AUTHOR_NAME": "wise-ci testkit",
    "GIT_AUTHOR_EMAIL": "testkit@wise-ci.invalid",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "wise-ci testkit",
    "GIT_COMMITTER_EMAIL": "testkit@wise-ci.invalid",
    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        env={**os.environ, **GIT_ISOLATION, **_IDENTITY},
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo(
    root: Path,
    files: dict[str, bytes],
    *,
    attributes: str | None = None,
    commit: bool = True,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    if attributes is not None:
        (root / ".gitattributes").write_text(attributes)
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    if commit:
        _git(root, "add", "-A")
        _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
    return root
