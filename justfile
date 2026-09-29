# Test tier: coverage-instrumented pytest run, combined across subprocesses,
# checked complete, then reported at the fail_under gate (pyproject.toml).
test:
    uv run --locked coverage erase
    uv run --locked coverage run -m pytest
    uv run --locked coverage combine
    PYTHONPATH=tooling uv run --locked python -m testkit.guards.coverage_completeness
    uv run --locked coverage report

verify: test
