"""Runs the requirements-tree gate: check_unreviewed, check_suspect_links, doorstop, then
check_method_consistency, check_text_citations, check_headers, check_citations, and
report_proposed, in that fixed order, every stage every run. A `check-reqs: <stage>` header
precedes each stage's own output; a stage whose precondition failed prints `not judged —
<reason>` instead of running it. Exits 1 if any stage failed or was not judged.

Three preconditions, checked in this order when more than one could apply to a stage:

- `doorstop` is not judged when `check_unreviewed` itself failed -- Doorstop writes review stamps,
  so running it over a tree check_unreviewed has not cleared would stamp a review nobody performed.
- `check_suspect_links`, `check_text_citations`, `check_headers` and `check_citations` are not
  judged when the requirements tree did not load -- each calls `doorstop.build()` directly, which
  crashes on a missing or empty document the same way `check_unreviewed` itself reports as a
  finding.
- `check_citations` is not judged outside a git working copy -- its own `git ls-files` calls would
  otherwise crash with no repository to search.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from . import (
    check_citations,
    check_headers,
    check_method_consistency,
    check_suspect_links,
    check_text_citations,
    check_unreviewed,
    report_proposed,
)


def _run_doorstop(root: Path) -> int:
    """Runs `doorstop --error-all --no-reformat` beside the running interpreter, working
    directory unchanged, its output passed through."""
    doorstop = Path(sys.executable).with_name("doorstop")
    return subprocess.run([str(doorstop), "--error-all", "--no-reformat"]).returncode


STAGES = (
    ("check_unreviewed", check_unreviewed.main),
    ("check_suspect_links", check_suspect_links.main),
    ("doorstop", _run_doorstop),
    ("check_method_consistency", check_method_consistency.main),
    ("check_text_citations", check_text_citations.main),
    ("check_headers", check_headers.main),
    ("check_citations", check_citations.main),
    ("report_proposed", report_proposed.main),
)

# The stages that call doorstop.build() directly, and so share check_unreviewed's own "did the
# tree load" precondition rather than the narrower "did check_unreviewed itself pass".
_TREE_GATED = ("check_suspect_links", "check_text_citations", "check_headers", "check_citations")


def main() -> int:
    parser = argparse.ArgumentParser(prog="check-reqs")
    parser.add_argument(
        "--root",
        default="docs/requirements",
        help="the directory holding the sys/srs/tst documents, resolved against the working directory",
    )
    args = parser.parse_args()
    root = Path.cwd() / args.root

    failed = False
    check_unreviewed_failed = False
    tree_loaded = True

    for name, stage in STAGES:
        print(f"check-reqs: {name}", flush=True)

        if name == "doorstop" and check_unreviewed_failed:
            reason = "check_unreviewed failed"
        elif name in _TREE_GATED and not tree_loaded:
            reason = "the requirements tree did not load"
        elif name == "check_citations" and not check_citations.in_git_working_copy():
            reason = "not a git working copy"
        else:
            reason = None

        if reason is not None:
            print(f"not judged — {reason}", flush=True)
            failed = True
            continue

        status = stage(root)
        if status != 0:
            failed = True
        if name == "check_unreviewed":
            check_unreviewed_failed = status != 0
            tree_loaded = check_unreviewed.tree_loads(root)

    return 1 if failed else 0
