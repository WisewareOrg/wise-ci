"""Specifies testkit.run.run_script / Result / ENV_ALLOW."""

import os
from pathlib import Path

from testkit.run import run_script

ECHO_ENV = (
    "import os\n"
    "for key in sorted(os.environ):\n"
    "    print(f'{key}={os.environ[key]}')\n"
)


def _write_script(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_run_script_returns_result_with_status_stdout_stderr(tmp_path):
    script = _write_script(
        tmp_path / "s.py",
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\nsys.exit(3)\n",
    )
    result = run_script(script, tmp_path)
    assert result.status == 3
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"


def test_run_script_home_is_not_the_real_home(tmp_path):
    script = _write_script(tmp_path / "home.py", ECHO_ENV)
    real_home = os.environ.get("HOME")
    result = run_script(script, tmp_path)
    seen = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert "HOME" in seen
    assert seen["HOME"] != real_home
    assert Path(seen["HOME"]).is_dir()


def test_run_script_env_allow_list_excludes_unlisted_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("TDD_RED_MARKER_NOT_ALLOWED", "leak")
    script = _write_script(tmp_path / "home.py", ECHO_ENV)
    result = run_script(script, tmp_path)
    assert "TDD_RED_MARKER_NOT_ALLOWED" not in result.stdout


def test_run_script_github_actions_absent_unless_passed(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    script = _write_script(tmp_path / "home.py", ECHO_ENV)
    result = run_script(script, tmp_path)
    assert "GITHUB_ACTIONS=" not in result.stdout


def test_run_script_env_param_is_passed_through(tmp_path):
    script = _write_script(tmp_path / "home.py", ECHO_ENV)
    result = run_script(script, tmp_path, env={"GITHUB_ACTIONS": "true"})
    assert "GITHUB_ACTIONS=true" in result.stdout


def test_run_script_coverage_prefixed_vars_pass_through(tmp_path, monkeypatch):
    marker = str(tmp_path / ".coverage.marker")
    monkeypatch.setenv("COVERAGE_FILE", marker)
    script = _write_script(tmp_path / "home.py", ECHO_ENV)
    result = run_script(script, tmp_path)
    assert f"COVERAGE_FILE={marker}" in result.stdout


def test_run_script_path_is_available_for_subprocesses(tmp_path):
    script = _write_script(
        tmp_path / "gitcheck.py",
        "import subprocess, sys\n"
        "r = subprocess.run(['git', '--version'], capture_output=True)\n"
        "sys.exit(0 if r.returncode == 0 else 1)\n",
    )
    result = run_script(script, tmp_path)
    assert result.status == 0
