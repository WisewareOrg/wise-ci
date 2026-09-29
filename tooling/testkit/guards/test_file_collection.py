"""testkit.guards.test_file_collection: every tracked test_*.py/*_test.py file must contribute at
least one collected item (plan #4 W2, decision 10; strategy §4 point 3).
"""

from pathlib import Path


def check(tracked_test_files: set[Path], collected_test_files: set[Path]) -> list[str]:
    return [
        f"{path}: tracked as a test file but collected no items"
        for path in sorted(tracked_test_files - collected_test_files)
    ]
