"""testkit.guards.coverage_completeness: every tracked Python file outside a top-level dot-directory
must be measured by the combined coverage data file in the current working directory (TESTING.md
D10: an empty or missing data file is an error, not a vacuous pass).

Run as `python -m testkit.guards.coverage_completeness` after `coverage combine`, from the repo
root (justfile).
"""

import subprocess
import sys
from pathlib import Path

from coverage.data import CoverageData


def _tracked_python_files(root: Path) -> set[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        (root / line).resolve()
        for line in result.stdout.splitlines()
        if not line.split("/", 1)[0].startswith(".")
    }


def main() -> int:
    root = Path.cwd()
    data = CoverageData(basename=str(root / ".coverage"))
    data.read()
    measured = {Path(path).resolve() for path in data.measured_files()}
    if not measured:
        print("coverage data file is empty or missing; nothing was measured.", file=sys.stderr)
        return 1
    unmeasured = sorted(_tracked_python_files(root) - measured)
    for path in unmeasured:
        print(f"not measured by coverage: {path.relative_to(root)}", file=sys.stderr)
    return 1 if unmeasured else 0


if __name__ == "__main__":
    sys.exit(main())
