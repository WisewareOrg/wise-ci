"""testkit.run.run_script: invoke a check script as a subprocess under a minimal, explicit
environment (plan #4 W2, decision 10).
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

ENV_ALLOW = ("PATH", "LANG", "LC_ALL")


@dataclass(frozen=True)
class Result:
    status: int
    stdout: str
    stderr: str


def run_script(script: Path, cwd: Path, *, env: dict[str, str] | None = None) -> Result:
    run_env = {name: os.environ[name] for name in ENV_ALLOW if name in os.environ}
    run_env.update((key, value) for key, value in os.environ.items() if key.startswith("COVERAGE_"))
    run_env["HOME"] = tempfile.mkdtemp()
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
