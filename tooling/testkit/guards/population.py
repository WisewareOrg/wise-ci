"""testkit.guards.population: every top-level check directory is populated (TESTING.md §4 point 2).
"""

from pathlib import Path

from testkit.discovery import check_dirs


def check(root: Path, collected_test_paths: set[Path]) -> list[str]:
    dirs = check_dirs(root)
    if not dirs:
        return [f"no check directories found under {root}"]
    problems = []
    for check_dir in dirs:
        if not (check_dir / "README.md").exists():
            problems.append(f"{check_dir.name}: no README.md")
        if not any(path.is_relative_to(check_dir / "tests") for path in collected_test_paths):
            problems.append(f"{check_dir.name}: no collected tests")
    return problems
