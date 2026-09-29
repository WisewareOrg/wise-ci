"""Specifies testkit.harness's own glue: the parts conftest.py's hook body delegates to so it stays
a straight-line sequence of calls (see harness.py's module docstring). Not testing any guard's own
decision logic — each guard is specified by its own test file.
"""

from pathlib import Path

from testkit.harness import (
    apply_guard_verdict,
    collected_ids_by_check,
    format_problems,
    skipped_or_xfailed_ids,
    tracked_test_files,
)
from testkit.repo import make_repo


class _FakeItem:
    def __init__(self, nodeid: str, markers: set[str]):
        self.nodeid = nodeid
        self._markers = markers

    def get_closest_marker(self, name: str):
        return name if name in self._markers else None


class _FakeCallspec:
    def __init__(self, test_id: str):
        self.id = test_id


class _FakeCollectedItem:
    def __init__(self, path: Path, test_id: str):
        self.path = path
        self.callspec = _FakeCallspec(test_id)


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


def test_format_problems_empty_writes_nothing():
    assert format_problems([]) == ""


def test_format_problems_prefixes_each_problem():
    assert format_problems(["x", "y"]) == "harness guard: x\nharness guard: y\n"


def test_collected_ids_by_check_does_not_pool_gap_ids_across_checks(tmp_path):
    # review-content (relayed via main): citation.check's cross-check pooling let check A's gap
    # test be satisfied by check B's README citing the same id. citation.py itself is unchanged
    # (called once per check dir with correctly scoped inputs, per builder); the fix is here --
    # this must never attribute a gap id collected under one check to another.
    dir_a = tmp_path / "check-a"
    dir_b = tmp_path / "check-b"
    item_a = _FakeCollectedItem(dir_a / "tests" / "test_cases.py", "gap-only-in-a")
    item_b = _FakeCollectedItem(dir_b / "tests" / "test_cases.py", "gap-only-in-b")
    result = collected_ids_by_check([dir_a, dir_b], [item_a, item_b])
    _, gaps_a = result[dir_a]
    _, gaps_b = result[dir_b]
    assert gaps_a == {"gap-only-in-a"}
    assert gaps_b == {"gap-only-in-b"}


def test_collected_ids_by_check_does_not_pool_collected_ids_across_checks(tmp_path):
    # Same defect, the other direction: a README citing an id collected only under a different
    # check must not read as satisfied just because the id was collected somewhere in the repo.
    dir_a = tmp_path / "check-a"
    dir_b = tmp_path / "check-b"
    item_a = _FakeCollectedItem(dir_a / "tests" / "test_cases.py", "must-pass-only-in-a")
    item_b = _FakeCollectedItem(dir_b / "tests" / "test_cases.py", "must-pass-only-in-b")
    result = collected_ids_by_check([dir_a, dir_b], [item_a, item_b])
    ids_a, _ = result[dir_a]
    ids_b, _ = result[dir_b]
    assert ids_a == {"must-pass-only-in-a"}
    assert ids_b == {"must-pass-only-in-b"}


def test_tracked_test_files_includes_both_tracked_spellings(tmp_path):
    # review-tests: no direct test existed at all -- only exercised incidentally by self-hosted
    # `just test` against the always-clean wise-ci tree.
    repo = make_repo(
        tmp_path / "repo",
        {
            "check-x/tests/test_a.py": b"def test_a():\n    assert True\n",
            "check-x/tests/b_test.py": b"def test_b():\n    assert True\n",
        },
    )
    result = tracked_test_files(repo)
    assert result == {
        (repo / "check-x/tests/test_a.py").resolve(),
        (repo / "check-x/tests/b_test.py").resolve(),
    }


def test_tracked_test_files_excludes_non_test_and_untracked_files(tmp_path):
    repo = make_repo(
        tmp_path / "repo",
        {
            "check-x/tests/test_a.py": b"def test_a():\n    assert True\n",
            "check-x/action.yml": b"runs: {}\n",
        },
    )
    (repo / "check-x/tests/test_untracked.py").write_text("def test_z():\n    assert True\n")
    result = tracked_test_files(repo)
    assert result == {(repo / "check-x/tests/test_a.py").resolve()}
