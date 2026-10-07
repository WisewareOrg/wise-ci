"""Fails when any item's `text` cites another item by identifier.

Builds the Doorstop tree rooted at the current working directory and scans each item's `text` for
an SYS/SRS/TST identifier, case-insensitively; `rationale` and `verification-justification` are not
scanned.
"""

import re
import sys
from pathlib import Path

import doorstop

# Case-insensitive: a mis-cased identifier defeats the rule exactly as an uppercase one does.
UID = re.compile(r"\b(?:SYS|SRS|TST)\d{3}\b", re.IGNORECASE)


def _cited():
    """Every item whose `text` names another item, with the identifiers it names."""
    cwd = str(Path.cwd())
    tree = doorstop.build(cwd=cwd, root=cwd)

    found = []
    for document in tree.documents:
        for item in document._iter():
            uids = sorted(set(UID.findall(item.text)))
            if uids:
                found.append((item.uid, uids))
    return sorted(found, key=lambda pair: str(pair[0]))


def main(root: Path) -> int:
    found = _cited()

    if found:
        print(f"{len(found)} item(s) cite another item in `text`:", file=sys.stderr)
        for uid, cites in found:
            print(f"  {uid} -> {', '.join(cites)}", file=sys.stderr)
        print(
            "\nAn obligation states what is required without a lookup. Rewrite the sentence to say"
            "\nthe thing itself, and move the citation to `rationale` or `verification-justification`"
            "\nif the relationship is worth recording.",
            file=sys.stderr,
        )
        return 1

    print("No item's `text` cites another item.")
    return 0
