"""Gathers real repository and pytest-session state and runs every conftest-wired guard against it.
Root conftest.py's own hook body stays a straight-line sequence of calls into this module, so the
guard-detected-problems path (which forces the session to fail, foreclosing that same run from ever
reaching `coverage report`) is exercised by direct unit tests here rather than by self-hosted
operation (plan #4 W2, decision 10; ADR 0001 rev 1 point 4).
"""

import re
import subprocess
from pathlib import Path

import yaml

from testkit.discovery import check_dirs
from testkit.guards import (
    citation,
    empty_run,
    file_collection,
    population,
    skip_ban,
    workflow_wiring,
)

_DIRECTION_ID = re.compile(r"^(?:must-fail|must-pass|gap)-")


def tracked_test_files(root: Path) -> set[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        (root / line).resolve()
        for line in result.stdout.splitlines()
        if Path(line).name.startswith("test_") or Path(line).name.endswith("_test.py")
    }


def _is_skipped_or_xfailed(item) -> bool:
    return bool(
        item.get_closest_marker("skip")
        or item.get_closest_marker("skipif")
        or item.get_closest_marker("xfail")
    )


def skipped_or_xfailed_ids(items) -> list[str]:
    return [item.nodeid for item in items if _is_skipped_or_xfailed(item)]


def direction_ids(items) -> tuple[set[str], set[str]]:
    ids = {
        item.callspec.id
        for item in items
        if hasattr(item, "callspec") and _DIRECTION_ID.match(item.callspec.id)
    }
    gap_ids = {test_id for test_id in ids if test_id.startswith("gap-")}
    return ids, gap_ids


def guard_problems(root: Path, items) -> list[str]:
    collected_paths = {item.path.resolve() for item in items}
    ids, gap_ids = direction_ids(items)
    dirs = check_dirs(root)
    workflow = yaml.safe_load((root / ".github" / "workflows" / "checks.yml").read_text())
    problems = []
    problems += empty_run.check(len(items))
    problems += population.check(root, collected_paths)
    problems += file_collection.check(tracked_test_files(root), collected_paths)
    problems += citation.check(dirs, ids, gap_ids)
    problems += skip_ban.check(skipped_or_xfailed_ids(items))
    problems += workflow_wiring.check(workflow, {d.name for d in dirs})
    return problems


def apply_guard_verdict(exitstatus: int, problems: list[str]) -> int:
    return 1 if problems else exitstatus


def format_problems(problems: list[str]) -> str:
    return "".join(f"harness guard: {problem}\n" for problem in problems)
