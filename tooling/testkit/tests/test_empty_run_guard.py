"""Specifies testkit.guards.empty_run (plan #4 W2, decision 10: "empty-run guard (pytest exit 5 →
non-zero)"; strategy §4 point 1).
"""

from testkit.guards.empty_run import check


def test_zero_collected_is_a_problem():
    assert check(0) != []


def test_nonzero_collected_is_clean():
    assert check(1) == []
