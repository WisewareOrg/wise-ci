"""testkit.run.run_script: invoke a check script as a subprocess under a minimal, explicit
environment (TESTING.md D5).
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from testkit.git_isolation import GIT_ISOLATION

ENV_ALLOW = ("PATH",)


@dataclass(frozen=True)
class Result:
    status: int
    stdout: str
    stderr: str


def run_script(script: Path, cwd: Path, *, env: dict[str, str] | None = None) -> Result:
    run_env = {name: os.environ[name] for name in ENV_ALLOW if name in os.environ}
    run_env.update((key, value) for key, value in os.environ.items() if key.startswith("COVERAGE_"))
    run_env.update(GIT_ISOLATION)
    run_env["LC_ALL"] = "C.UTF-8"
    run_env["HOME"] = tempfile.mkdtemp()
    run_env["GIT_CEILING_DIRECTORIES"] = str(cwd)
    if env:
        run_env.update(env)
    result = subprocess.run(
        ["python3", str(script)],
        cwd=cwd,
        env=run_env,
        capture_output=True,
        text=True,
    )
    return Result(status=result.returncode, stdout=result.stdout, stderr=result.stderr)
