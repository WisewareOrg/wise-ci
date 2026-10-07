"""Fails when any item's header is empty, carries a character outside the permitted set, or is a
case-insensitive prefix of another item's header.

Builds the Doorstop tree rooted at the current working directory, folds each header's whitespace
to single spaces, and compares it against the allowlist
`A-Z a-z 0-9 space , . ' ( ) & : ; -`.
"""

import re
import sys
from pathlib import Path

import doorstop

PERMITTED = re.compile(r"^[A-Za-z0-9 ,.'()&:;-]+$")


def _headers():
    """Every item's UID and its header, whitespace folded to single spaces and trimmed."""
    cwd = str(Path.cwd())
    tree = doorstop.build(cwd=cwd, root=cwd)
    for document in tree.documents:
        for item in document._iter():
            yield str(item.uid), " ".join(
                part for part in re.split(r"[ \t\r\n\f\v]+", item.header or "") if part
            )


def main(root: Path) -> int:
    problems = []
    known = list(_headers())

    for uid, header in known:
        if not header:
            problems.append(f"{uid}  has no header")
        elif not PERMITTED.match(header):
            outside = sorted({c for c in header if not PERMITTED.match(c)})
            problems.append(
                f"{uid}  header uses {' '.join(repr(c) for c in outside)}, outside the permitted set"
            )

    # Each pair once, in one direction; no word boundary, since the pairs that matter continue
    # with punctuation.
    for uid, header in known:
        for other, other_header in known:
            if uid >= other or not header:
                continue
            if other_header.casefold() == header.casefold():
                problems.append(f"{uid}  and {other}  carry the same header")
            elif other_header.casefold().startswith(header.casefold()):
                problems.append(f"{uid}  header is a prefix of {other}'s — a reader tells them apart only at the end")
            elif header.casefold().startswith(other_header.casefold()):
                problems.append(f"{other}  header is a prefix of {uid}'s — a reader tells them apart only at the end")

    if problems:
        print(f"{len(problems)} malformed header(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"Every header is non-empty, within the permitted set, and prefix-free ({len(known)} items).")
    return 0
