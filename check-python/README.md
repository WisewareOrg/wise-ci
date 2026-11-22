# check-python

Runs the org Python standard against the repository at the working directory: `ruff check`,
`ruff format --check`, `interrogate`, `pydoclint` and `ty check`, in that order, every tool every
run. Each tool's own output follows a `check-python: <name>` header, unfiltered. Exits 1 if any tool
failed or was not judged. The tools are `==`-pinned in this package, so CI and a local run use the
same versions; why it is built this way is
[ADR 0002 rev 1](../docs/decisions/0002-org-python-standards-in-wise-ci.md)'s.

- interrogate runs at `--fail-under 100 -vv --omit-covered-files`, and pydoclint with the Google style, type hints in
  signatures and not in docstrings, return types unchecked, short docstrings checked and `__init__`
  docstrings allowed; both receive `git ls-files '*.py'`, so every tracked Python file is in scope.
- ruff and ty honour `.gitignore`. ruff reads the repository's own `[tool.ruff]`, which
  [`../check-python-floor/README.md`](../check-python-floor/README.md) holds to the floor. ty runs on
  its default rules against `./.venv`.

**A repository tracking no `.py` file passes** with the one line `check-python: no Python — no
tracked .py files.` and no tool runs, as `check-python-floor` does.

**Run with no `.venv` at the working directory, and ty prints `not judged — no .venv at ./.venv; run
uv sync first`**, counts as failed, and the other four tools still run. ty is never left to find an
interpreter itself, which would silently resolve against the wrong environment.

**What this does not catch:** anything ty cannot see without a build. A repository with compiled or
generated modules must build them before running this check, or ty reports them unresolved.

## Run locally

Install the distribution as described in [`../README.md`](../README.md) § Consuming a check, sync the
repository, then run it from the repository root:

```sh
uv run --locked check-python
```

No arguments and no environment variables.

Run it from the root of the repository it checks: the repository is the working directory, so a run
from a subfolder sees only that subtree, and a subtree with no `.py` file passes with the no-Python
line.
