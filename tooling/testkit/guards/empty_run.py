"""testkit.guards.empty_run: pytest's own exit 5 (no tests collected) must fail the session
explicitly (TESTING.md §4 point 1).
"""


def check(collected_count: int) -> list[str]:
    if collected_count == 0:
        return ["no tests were collected"]
    return []
