"""Specifies testkit.guards.coverage_completeness as a CLI module (plan #4 W2; strategy D10;
settled with builder: invoked as `python -m testkit.guards.coverage_completeness` after `coverage
combine`, not as a pytest-collected test). Exits non-zero on an unmeasured in-scope tracked *.py
file, or on an empty or missing coverage data file (D10: "not 0 of 0").
"""

import os
import subprocess
import sys
from pathlib import Path

from coverage.data import CoverageData

REPO_ROOT = Path(__file__).resolve().parents[3]


def _init_repo(root: Path, py_files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in py_files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "seed"],
        cwd=root,
        check=True,
    )
    return root


def _measure(repo: Path, *measured: str) -> None:
    # A nested coverage.Coverage() would install a second sys.settrace tracer, displacing the
    # outer `just test` run's own tracer for as long as it's active — making the lines in between
    # unmeasurable from the outside (builder, found running this file under `just test`).
    # CoverageData writes measurement records directly, with no tracer involved.
    data = CoverageData(basename=str(repo / ".coverage"))
    data.add_lines({str(repo / rel): {1} for rel in measured})
    data.write()


def _run_guard(cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "tooling")
    return subprocess.run(
        [sys.executable, "-m", "testkit.guards.coverage_completeness"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def test_unmeasured_tracked_file_is_a_problem(tmp_path):
    repo = _init_repo(
        tmp_path,
        {"module_a.py": "def a():\n    return 1\n", "module_b.py": "def b():\n    return 2\n"},
    )
    _measure(repo, "module_a.py")
    result = _run_guard(repo)
    assert result.returncode != 0
    assert "ModuleNotFoundError" not in result.stderr


def test_missing_coverage_data_file_is_a_problem(tmp_path):
    repo = _init_repo(tmp_path, {"module_a.py": "def a():\n    return 1\n"})
    result = _run_guard(repo)
    assert result.returncode != 0
    assert "ModuleNotFoundError" not in result.stderr


def test_empty_coverage_data_file_is_a_problem_even_with_no_population(tmp_path):
    repo = _init_repo(tmp_path, {"README.md": "# empty\n"})
    (repo / ".coverage").write_bytes(b"")
    result = _run_guard(repo)
    assert result.returncode != 0
    assert "ModuleNotFoundError" not in result.stderr


def test_fully_measured_tracked_files_is_clean(tmp_path):
    repo = _init_repo(
        tmp_path,
        {"module_a.py": "def a():\n    return 1\n", "module_b.py": "def b():\n    return 2\n"},
    )
    _measure(repo, "module_a.py", "module_b.py")
    result = _run_guard(repo)
    assert result.returncode == 0
