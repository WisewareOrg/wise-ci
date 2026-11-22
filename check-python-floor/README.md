# check-python-floor

Holds the repository's root `pyproject.toml` to the org Python floor, so a repository's ruff
configuration cannot drift from the standard `check-python` assumes. Passes with a `no Python` line,
without reading `pyproject.toml`, when `git ls-files '*.py'` is empty. Otherwise:

- a root `pyproject.toml` must exist;
- `[tool.ruff]` may hold only `line-length = 120`, `lint.select` equal as a set to
  `E, F, W, I, UP, B, SIM, D, D417`, `lint.pydocstyle.convention = "google"`, and `src` (any value,
  never judged); any other key, or a different value, fails;
- `[tool.ty]`, `[tool.interrogate]` and `[tool.pydoclint]` must be absent;
- `requires-python` must be present with a lower bound of at least 3.12;
- no tracked `ruff.toml`, `.ruff.toml` or `ty.toml` exists anywhere, and no `pyproject.toml` below
  the root has a `[tool.ruff]` or `[tool.ty]`, since either would configure the tool outside the
  allowlist.

One stderr line per violation, `pyproject.toml: [<table>] <key>: <reason>`, in a fixed order, no
summary; a pass prints `check-python-floor: pyproject.toml meets the floor.`. The floor is data at
the top of [`check_python_floor/__init__.py`](check_python_floor/__init__.py).

**What this does not catch:** that the repository runs `check-python` at all, or that it passes. The
floor holds the configuration only.

## Run locally

Install the distribution as described in [`../README.md`](../README.md) § Consuming a check, then run
it from the repository root:

```sh
uv run --locked check-python-floor
```

No arguments and no environment variables.
