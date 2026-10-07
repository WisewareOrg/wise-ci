"""Prints the `proposed`-item backlog per tier; never fails.

Walks every `.doorstop.yml` below `root`, counting each document's items by `status`, defaulting
to the document's own `attributes.defaults.status` where an item carries none, and listing any
status outside `proposed` | `accepted`.
"""

import sys
from pathlib import Path

import yaml

STATUSES = ("proposed", "accepted")

# Tiers print in tree order, parent first; a prefix outside this tuple prints after them.
TIER_ORDER = ("SYS", "SRS", "TST")


def _load(root: Path):
    """Item statuses per document prefix, read from each document's own `.doorstop.yml`."""
    tiers = {}
    for config in sorted(root.rglob(".doorstop.yml")):
        document = config.parent
        if any(part.startswith(".") for part in document.relative_to(root).parts):
            continue  # a dotfile directory, such as `.venv`, holds no item
        settings = yaml.safe_load(config.read_text()) or {}
        prefix = str((settings.get("settings") or {}).get("prefix") or document.name)
        default = ((settings.get("attributes") or {}).get("defaults") or {}).get("status")
        tier = tiers.setdefault(prefix, {"total": 0, "proposed": [], "unplaced": []})
        for path in sorted([*document.glob("*.yml"), *document.glob("*.yaml")]):
            if path.stem.startswith("."):
                continue  # the document's own .doorstop.yml, not an item
            item = yaml.safe_load(path.read_text()) or {}
            status = str(item.get("status", default) or "").strip()
            tier["total"] += 1
            if status == "proposed":
                tier["proposed"].append(path.stem)
            elif status not in STATUSES:
                tier["unplaced"].append(f"{path.stem} ({status or 'unset'})")
    return tiers


def main(root: Path) -> int:
    tiers = _load(root)
    ordered = [p for p in TIER_ORDER if p in tiers] + sorted(set(tiers) - set(TIER_ORDER))

    print("proposed backlog (reported, never gating):")
    for prefix in ordered:
        tier = tiers[prefix]
        listed = f": {' '.join(tier['proposed'])}" if tier["proposed"] else ""
        print(f"  {prefix}: {len(tier['proposed'])} of {tier['total']} item(s) proposed{listed}")
    unplaced = [entry for prefix in ordered for entry in tiers[prefix]["unplaced"]]
    if unplaced:
        print(
            f"  {len(unplaced)} item(s) carry a status outside proposed | accepted, counted in "
            f"neither: {' '.join(unplaced)}"
        )
    total = sum(tier["total"] for tier in tiers.values())
    backlog = sum(len(tier["proposed"]) for tier in tiers.values())
    print(f"  {backlog} of {total} item(s) in the tree await baselining.")
    return 0
