"""Wires tooling/testkit/guards/ into every pytest session run against this repository
(ADR 0001 rev 1 point 4).
"""

import sys
from pathlib import Path

from testkit.harness import apply_guard_verdict, format_problems, guard_problems

ROOT = Path(__file__).resolve().parent


def pytest_sessionfinish(session, exitstatus):
    problems = guard_problems(ROOT, session.items)
    sys.stdout.write(format_problems(problems))
    session.exitstatus = apply_guard_verdict(exitstatus, problems)
