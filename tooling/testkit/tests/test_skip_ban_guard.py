"""Specifies testkit.guards.skip_ban. TESTING.md D8: no skip, no xfail, anywhere."""

from testkit.guards.skip_ban import check


def test_any_skipped_or_xfailed_id_is_a_problem():
    assert check(["must-pass-something"]) != []


def test_no_skipped_or_xfailed_ids_is_clean():
    assert check([]) == []
