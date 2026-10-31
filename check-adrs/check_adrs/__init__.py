"""Runs check-adrs's two halves, one after the other: the index half
(check_adr_index.main()), then the revs half (check_adr_revs.main()), even if the index half
failed or crashed. See check-adrs/README.md.

The repository is the working directory: an action's script runs from the consumer's checkout.
"""

import traceback

from check_adrs import check_adr_index, check_adr_revs


def _run_half(half_main) -> bool:
    """True if `half_main` failed, whether by returning non-zero or by raising. An exception's
    traceback is printed to stderr — the same text Python prints for one left uncaught — and
    counts as a failure."""
    try:
        return half_main() != 0
    except Exception:
        traceback.print_exc()
        return True


def main() -> int:
    index_failed = _run_half(check_adr_index.main)
    revs_failed = _run_half(check_adr_revs.main)
    return 1 if index_failed or revs_failed else 0
