"""Specifies testkit.guards.population. TESTING.md §4 point 2: every top-level dir with
action.yml/action.yaml is a check; zero checks, a check with 0 collected tests, or a check with no
README fails.
"""

from pathlib import Path

from testkit.guards.population import check


def _make_check(root: Path, name: str, *, manifest: str = "action.yml", readme: bool = True) -> Path:
    check_dir = root / name
    (check_dir / "tests").mkdir(parents=True)
    (check_dir / manifest).write_text("runs:\n  using: composite\n")
    if readme:
        (check_dir / "README.md").write_text(f"# {name}\n")
    return check_dir


def test_zero_checks_is_a_problem(tmp_path):
    assert check(tmp_path, set()) != []


def test_check_with_no_collected_tests_is_a_problem(tmp_path):
    _make_check(tmp_path, "sample-check")
    assert check(tmp_path, set()) != []


def test_check_with_no_readme_is_a_problem(tmp_path):
    check_dir = _make_check(tmp_path, "sample-check", readme=False)
    test_file = check_dir / "tests" / "test_a.py"
    test_file.write_text("def test_a():\n    assert True\n")
    assert check(tmp_path, {test_file}) != []


def test_check_with_manifest_readme_and_a_collected_test_is_clean(tmp_path):
    check_dir = _make_check(tmp_path, "sample-check")
    test_file = check_dir / "tests" / "test_a.py"
    test_file.write_text("def test_a():\n    assert True\n")
    assert check(tmp_path, {test_file}) == []


def test_action_yaml_spelling_is_also_recognised_as_a_check(tmp_path):
    check_dir = _make_check(tmp_path, "sample-check", manifest="action.yaml")
    test_file = check_dir / "tests" / "test_a.py"
    test_file.write_text("def test_a():\n    assert True\n")
    assert check(tmp_path, {test_file}) == []
