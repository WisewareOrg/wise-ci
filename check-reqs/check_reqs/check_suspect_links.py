"""Fails when an inactive item's link stamp no longer matches its parent's, or names a parent the
tree does not hold.

Builds the Doorstop tree rooted at the current working directory and compares every inactive
item's link stamp against its parent's own stamp, inactive items included.
"""

import sys
from pathlib import Path

import doorstop


def _suspect():
    """The tree's inactive items whose link stamp no longer matches their parent's, and every
    inactive link naming a parent the tree does not hold."""
    cwd = str(Path.cwd())
    tree = doorstop.build(cwd=cwd, root=cwd)

    by_uid = {}
    for document in tree.documents:
        for item in document._iter():
            by_uid[item.uid] = item

    found, dangling = [], []
    for item in by_uid.values():
        if item.active:
            continue
        for uid in item.links:
            parent = by_uid.get(uid)
            if parent is None:
                dangling.append((item.uid, uid))
                continue
            if not uid.stamp:
                continue  # never stamped: check_unreviewed's, and it runs first
            if uid.stamp != parent.stamp():
                found.append((item.uid, uid))
    return (
        sorted(found, key=lambda pair: (str(pair[0]), str(pair[1]))),
        sorted(dangling, key=lambda pair: (str(pair[0]), str(pair[1]))),
    )


def main(root: Path) -> int:
    found, dangling = _suspect()

    if dangling:
        print(f"{len(dangling)} inactive item link(s) name a parent the tree does not hold:", file=sys.stderr)
        for child, parent in dangling:
            print(f"  {child} -> {parent}", file=sys.stderr)
        print("\nPoint each at a parent some document holds, or delete the link.", file=sys.stderr)

    if found:
        if dangling:
            print(file=sys.stderr)
        print(f"{len(found)} inactive item link(s) are suspect:", file=sys.stderr)
        for child, parent in found:
            print(f"  {child} -> {parent}", file=sys.stderr)
        print(
            "\nThe parent's fingerprint no longer matches the stamp this link carries: either the"
            "\nparent changed after the link was reviewed, or the link was pointed at a different"
            "\nparent. Doorstop cannot see it, because the child is inactive. Re-read the item"
            "\nagainst the parent it now has, then re-stamp it — which is not a CLI operation:"
            "\n`Tree.find_item` is active-only, so `doorstop review` and `doorstop clear` both"
            "\nanswer `no item with UID` for an inactive item.",
            file=sys.stderr,
        )

    if found or dangling:
        return 1

    print("Every inactive item's links resolve and match the parents they were reviewed against.")
    return 0
