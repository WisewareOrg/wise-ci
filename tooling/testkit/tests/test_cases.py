"""Specifies testkit.cases.Case / case_id (owner, 2026-09-28: no origin field on Case)."""

import pytest

from testkit.cases import Case, case_id


@pytest.mark.parametrize("direction", ["must-fail", "must-pass", "gap"])
def test_case_id_is_direction_dash_slug(direction):
    case = Case(slug="crlf-tracked-txt", row="a tracked file containing CRLF", direction=direction)
    assert case_id(case) == f"{direction}-crlf-tracked-txt"


def test_case_fields_are_exactly_slug_row_direction():
    case = Case(slug="s", row="r", direction="must-fail")
    assert case.slug == "s"
    assert case.row == "r"
    assert case.direction == "must-fail"
    assert not hasattr(case, "origin")
