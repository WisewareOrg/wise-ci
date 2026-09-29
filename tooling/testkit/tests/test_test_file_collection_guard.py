"""Specifies testkit.guards.test_file_collection (plan #4 W2, decision 10; strategy §4 point 3:
every tracked test_*.py or *_test.py contributes at least one collected item.
"""

from testkit.guards.test_file_collection import check


def test_uncollected_tracked_test_file_is_a_problem(tmp_path):
    tracked = tmp_path / "check-x" / "tests" / "test_a.py"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("def test_a():\n    assert True\n")
    assert check({tracked}, set()) != []


def test_uncollected_tracked_alt_spelling_test_file_is_a_problem(tmp_path):
    tracked = tmp_path / "check-x" / "tests" / "a_test.py"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("def test_a():\n    assert True\n")
    assert check({tracked}, set()) != []


def test_collected_tracked_test_file_is_clean(tmp_path):
    tracked = tmp_path / "check-x" / "tests" / "test_a.py"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("def test_a():\n    assert True\n")
    assert check({tracked}, {tracked}) == []


def test_collected_tracked_alt_spelling_test_file_is_clean(tmp_path):
    tracked = tmp_path / "check-x" / "tests" / "a_test.py"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("def test_a():\n    assert True\n")
    assert check({tracked}, {tracked}) == []
