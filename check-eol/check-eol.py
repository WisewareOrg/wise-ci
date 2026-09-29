#!/usr/bin/env python3
"""Every file git treats as text is LF-only, over the whole tracked tree.

`.gitattributes` decides which files git treats as text.

The population is the tracked set, so an untracked, non-ignored file is invisible to the search and
is reported as unsearchable rather than silently unsearched — visibility fails it, not content. The
pairing with `check-untracked.py` is defence-in-depth, per docs/CI.md § Repository shape. Both
findings accumulate in one run rather than short-circuiting, so an untracked file beside a CRLF
defect is one visit, not two.

`git grep -lI` skips binary content; `-P` gives `\r` its perl-regex meaning. Exit 0 is a match —
this check's failure case — and 1 is none, which over an empty tracked tree reports success
(README.md's empty-scan ruling). Any other status is the search itself failing, and is propagated.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()


def main():
    problems = False

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if untracked.returncode != 0:
        sys.stderr.write(untracked.stderr)
        return untracked.returncode
    if untracked.stdout:
        sys.stderr.write(untracked.stdout)
        print("untracked, so this check cannot search them — git add or gitignore each.", file=sys.stderr)
        problems = True

    search = subprocess.run(
        ["git", "grep", "-lIP", r"\r$", "--", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if search.returncode == 0:
        sys.stdout.write(search.stdout)
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error::CRLF line endings found in the files above; the repo is LF-only (.gitattributes).")
        else:
            print("CRLF found in the files above; the repo is LF-only (.gitattributes).", file=sys.stderr)
        problems = True
    elif search.returncode != 1:
        sys.stderr.write(search.stderr)
        return search.returncode

    if problems:
        return 1
    print("No CRLF line endings in the tracked tree; no untracked file left unsearched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
