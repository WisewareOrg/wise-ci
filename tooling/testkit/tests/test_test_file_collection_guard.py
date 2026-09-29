"""Specifies testkit.guards.file_collection. §4 point 3: every tracked test_*.py or *_test.py
contributes at least one collected item. Module renamed from test_file_collection.py so its own
filename stops matching the heuristic it checks for.
"""

from testkit.guards.file_collection import check


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
