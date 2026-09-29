"""testkit.guards.skip_ban: no test may skip or xfail, anywhere (TESTING.md D8).
"""


def check(skipped_or_xfailed_ids: list[str]) -> list[str]:
    return [f"{test_id}: skipped or xfailed, which this gate never permits" for test_id in skipped_or_xfailed_ids]
