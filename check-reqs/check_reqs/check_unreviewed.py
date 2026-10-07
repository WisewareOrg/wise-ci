"""Fails when any item or link under `root` carries no review fingerprint.

Walks every `.doorstop.yml` below `root`; a `reviewed` value counts as unstamped unless it is a
non-empty string, and a link's stamp counts as unstamped when it is, or its own item is.
"""

import sys
from pathlib import Path

import yaml

REQUIRED_SILOS = ("sys", "srs", "tst")


def _unstamped(value) -> bool:
    """True unless `value` is a non-empty string."""
    return not isinstance(value, str) or not value.strip()


def _load(root: Path):
    """Reads every item from every `.doorstop.yml` document below `root`. A link is a bare string
    or a single-key mapping whose value is the stamp or `None`."""
    unreviewed, unstamped, counts = [], [], {}
    for config in sorted(root.rglob(".doorstop.yml")):
        document = config.parent
        silo = document.relative_to(root).as_posix()
        if any(part.startswith(".") for part in document.relative_to(root).parts):
            continue  # a dotfile directory, such as `.venv`, holds no item
        counts[silo] = 0
        for path in sorted([*document.glob("*.yml"), *document.glob("*.yaml")]):
            if path.stem.startswith("."):
                continue  # the document's own .doorstop.yml, not an item
            item = yaml.safe_load(path.read_text()) or {}
            uid = path.stem
            counts[silo] += 1
            item_unreviewed = _unstamped(item.get("reviewed"))
            if item_unreviewed:
                unreviewed.append(uid)
            for link in item.get("links") or []:
                parent = next(iter(link)) if isinstance(link, dict) else link
                stamp = link[parent] if isinstance(link, dict) else None
                if _unstamped(stamp) or item_unreviewed:
                    unstamped.append(f"{uid} -> {parent}")
    return unreviewed, unstamped, counts


def main(root: Path) -> int:
    unreviewed, unstamped, counts = _load(root)

    empty = sorted(s for s, n in counts.items() if not n)
    absent = [s for s in REQUIRED_SILOS if s not in counts]
    if empty or absent:
        for silo in absent:
            print(f"{root / silo}/ holds no document — missing, renamed, or deleted.", file=sys.stderr)
        for silo in empty:
            print(f"{root / silo}/ yielded no item — this check read none of it.", file=sys.stderr)
        print(
            "\nA tier that yields nothing produces no finding, which reads exactly like a tier whose"
            "\nevery item is reviewed.",
            file=sys.stderr,
        )
        return 1

    if unreviewed:
        print(f"{len(unreviewed)} item(s) carry no review fingerprint:", file=sys.stderr)
        for prefix in ("SYS", "SRS", "TST"):
            tier = [u for u in unreviewed if u.startswith(prefix)]
            if tier:
                print(f"  {prefix} ({len(tier)}): {' '.join(tier)}", file=sys.stderr)

    if unstamped:
        print(f"\n{len(unstamped)} link(s) were never reviewed against their parent:", file=sys.stderr)
        for line in unstamped:
            print(f"  {line}", file=sys.stderr)

    if unreviewed or unstamped:
        print(
            "\nDoorstop would stamp every one of these on its next run, recording a review nobody"
            "\nperformed. Read the item against its parent and run `doorstop review <uid>`, or"
            "\ndelete it. Do not clear this by running the gate.",
            file=sys.stderr,
        )
        return 1

    print("Every item and every link carries a review fingerprint.")
    return 0
