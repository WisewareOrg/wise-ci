"""Specifies testkit.harness's own glue: the parts conftest.py's hook body delegates to so it stays
a straight-line sequence of calls (see harness.py's module docstring). Not testing any guard's own
decision logic — each guard is specified by its own test file.
"""

from testkit.harness import apply_guard_verdict, skipped_or_xfailed_ids


class _FakeItem:
    def __init__(self, nodeid: str, markers: set[str]):
        self.nodeid = nodeid
        self._markers = markers

    def get_closest_marker(self, name: str):
        return name if name in self._markers else None


def test_apply_guard_verdict_forces_failure_when_problems_exist():
    assert apply_guard_verdict(0, ["something wrong"]) == 1


def test_apply_guard_verdict_leaves_exitstatus_when_clean():
    assert apply_guard_verdict(0, []) == 0


def test_skipped_or_xfailed_ids_includes_a_marked_item():
    item = _FakeItem("test_x.py::test_thing", {"skip"})
    assert skipped_or_xfailed_ids([item]) == ["test_x.py::test_thing"]


def test_skipped_or_xfailed_ids_excludes_an_unmarked_item():
    item = _FakeItem("test_x.py::test_thing", set())
    assert skipped_or_xfailed_ids([item]) == []
