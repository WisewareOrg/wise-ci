"""Specifies testkit.guards.citation (plan #4 W2, decision 10; strategy §4 point 4: every README
citation is a collected test id, and every direction=gap test id is cited by its README, both
directions.
"""

from pathlib import Path

from testkit.guards.citation import check


def _readme(check_dir: Path, text: str) -> Path:
    check_dir.mkdir(parents=True)
    path = check_dir / "README.md"
    path.write_text(text)
    return path


def test_citing_an_uncollected_id_is_a_problem(tmp_path):
    check_dir = tmp_path / "check-x"
    _readme(check_dir, "See `must-fail-crlf` for the row.\n")
    assert check([check_dir], set(), set()) != []


def test_an_uncited_gap_id_is_a_problem(tmp_path):
    check_dir = tmp_path / "check-x"
    _readme(check_dir, "Nothing cited here.\n")
    assert check([check_dir], {"gap-binary-attribute"}, {"gap-binary-attribute"}) != []


def test_citing_a_collected_id_and_every_gap_id_is_clean(tmp_path):
    check_dir = tmp_path / "check-x"
    _readme(check_dir, "See `must-fail-crlf` and `gap-binary-attribute`.\n")
    collected = {"must-fail-crlf", "gap-binary-attribute"}
    assert check([check_dir], collected, {"gap-binary-attribute"}) == []
