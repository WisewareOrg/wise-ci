"""Fails when an item carries no verification-justification, an unrecognised verification-method,
or sits at a method its own children do not support.

Loads every item under the three required silos below `root`. `verification-method` ranks by
mechanical decidability (`test` > `analysis` > `inspection` > `demonstration`); a parent's rank must
equal its least-decidable child's, unless it sits below with a verification-justification.
"""

import sys
from pathlib import Path

import yaml

RANK = {"test": 4, "analysis": 3, "inspection": 2, "demonstration": 1}


def _load(root: Path):
    """Reads every item's `verification-method`, parent links, and whether it is normative and
    justified, from the three required silos below `root`."""
    method, children, justified, obliging = {}, {}, set(), set()
    for silo in ("sys", "srs", "tst"):
        for path in sorted([*(root / silo).glob("*.yml"), *(root / silo).glob("*.yaml")]):
            if path.stem.startswith("."):
                continue  # the silo's own .doorstop.yml, not an item
            item = yaml.safe_load(path.read_text()) or {}
            uid = path.stem
            method[uid] = str(item.get("verification-method") or "").strip()
            if item.get("normative") is not False:
                obliging.add(uid)
            if str(item.get("verification-justification") or "").strip():
                justified.add(uid)
            for link in item.get("links") or []:
                parent = next(iter(link)) if isinstance(link, dict) else link
                children.setdefault(str(parent), []).append(uid)
    return method, children, justified, obliging


def main(root: Path) -> int:
    method, children, justified, obliging = _load(root)
    unjustified = sorted(obliging - justified)
    unranked = sorted(uid for uid in obliging if method[uid] not in RANK)
    failures = []
    for parent, kids in sorted(children.items()):
        rank = RANK.get(method.get(parent, ""))
        kid_ranks = [RANK[method[k]] for k in kids if method.get(k) in RANK]
        if rank is None or not kid_ranks:
            continue
        least = min(kid_ranks)
        if rank == least:
            continue
        if rank < least and parent in justified:
            continue  # residual obligation no child carries, argued in the justification
        weakest = ", ".join(f"{k} ({method[k]})" for k in kids if RANK.get(method[k]) == least)
        if rank > least:
            reason = "above its least-decidable child"
        else:
            reason = "below every child with no verification-justification"
        failures.append(f"{parent} ({method[parent]}) is {reason}: {weakest}")

    if unjustified:
        print(f"{len(unjustified)} item(s) carry no verification-justification:", file=sys.stderr)
        for prefix in ("SYS", "SRS", "TST"):
            tier = [u for u in unjustified if u.startswith(prefix)]
            if tier:
                print(f"  {prefix} ({len(tier)}): {' '.join(tier)}", file=sys.stderr)
        print(
            "\nEvery item states what its verification settles and what it does not: below `test`,"
            "\nwhat blocks a mechanical check; at `test`, what the check leaves unproven"
            "\n(check-reqs/README.md § check_method_consistency).",
            file=sys.stderr,
        )

    if unranked:
        print(f"\n{len(unranked)} item(s) carry an unrecognised verification-method:", file=sys.stderr)
        for uid in unranked:
            print(f"  {uid}  '{method[uid]}' is not one of {', '.join(RANK)}", file=sys.stderr)
        print(
            "\nAn unrecognised value ranks as nothing, so the rule above cannot judge the item and"
            "\nwould pass it in silence. Spell the method as one of the four"
            "\n(check-reqs/README.md § check_method_consistency).",
            file=sys.stderr,
        )

    if failures:
        print("\nVerification-method inconsistency:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            f"\n{len(failures)} item(s). A parent is verified by the aggregate of its children, so it"
            "\ncan be no more decidable than the least. Promote the lagging child, split the parent so"
            "\neach clause sits at its own honest method, or - where the parent holds a residue no child"
            "\ncarries - record a verification-justification"
            "\n(check-reqs/README.md § check_method_consistency).",
            file=sys.stderr,
        )

    if unjustified or unranked or failures:
        return 1

    print(
        f"All {len(obliging)} obliging item(s) carry a verification-justification; methods are "
        f"consistent across {len(children)} parent items."
    )
    return 0
