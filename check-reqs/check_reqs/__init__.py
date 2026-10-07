"""Runs the requirements-tree gate: check_unreviewed, check_suspect_links, doorstop, then
check_method_consistency, check_text_citations, check_headers, and report_proposed, in that fixed
order. Stops at the first stage returning non-zero, with that stage's own exit status; a
`check-reqs: <stage>` header precedes each stage's own output.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from . import (
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
    ("report_proposed", report_proposed.main),
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="check-reqs")
    parser.add_argument(
        "--root",
        default="docs/requirements",
        help="the directory holding the sys/srs/tst documents, resolved against the working directory",
    )
    args = parser.parse_args()
    root = Path.cwd() / args.root

    for name, stage in STAGES:
        print(f"check-reqs: {name}", flush=True)
        status = stage(root)
        if status != 0:
            return status
    return 0
