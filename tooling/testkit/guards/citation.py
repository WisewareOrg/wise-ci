"""testkit.guards.citation: every README citation is a collected test id, and every gap-direction
test id is cited by its README (plan #4 W2, decision 10; strategy §4 point 4).
"""

import re
from pathlib import Path

_CITATION = re.compile(r"`((?:must-fail|must-pass|gap)-[a-z0-9-]+)`")


def _cited_ids(check_dirs: list[Path]) -> set[str]:
    ids = set()
    for check_dir in check_dirs:
        ids.update(_CITATION.findall((check_dir / "README.md").read_text()))
    return ids


def check(check_dirs: list[Path], collected_test_ids: set[str], gap_test_ids: set[str]) -> list[str]:
    cited = _cited_ids(check_dirs)
    problems = [f"README cites {test_id!r}, which was not collected" for test_id in sorted(cited - collected_test_ids)]
    problems += [f"{test_id!r} is a gap case, not cited by any README" for test_id in sorted(gap_test_ids - cited)]
    return problems
