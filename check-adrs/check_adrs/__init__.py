"""Runs the ADR gate: check_adr_index, then check_adr_revs, every stage every run. Exits 1 if
either stage failed; a `check-adrs: <stage>` header precedes each stage's own output.

The repository is the working directory: an action's script runs from the consumer's checkout.
"""

from pathlib import Path

from . import check_adr_index, check_adr_revs

STAGES = (
    ("check_adr_index", check_adr_index.main),
    ("check_adr_revs", check_adr_revs.main),
)


def main() -> int:
    root = Path.cwd()

    failed = False
    for name, stage in STAGES:
        print(f"check-adrs: {name}", flush=True)
        if stage(root) != 0:
            failed = True
    return 1 if failed else 0
