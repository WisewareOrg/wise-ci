#!/usr/bin/env bash
# Combines every check's coverage data and reports it, failing under 100%. With no argument,
# guards the full population first (tooling/coverage-population.sh) — a check folder with no
# tests, or one not wired in, counts as untested and fails the report. With a check's folder name
# as the one argument, scopes the report to that check alone and skips the population guard,
# which is a repo-wide concern. Shared between ci.yml's ci job and `just test`
# (docs/TESTING.md § In CI). Run from the repository root, after every check's own coverage run.
set -euo pipefail

check="${1:-}"

uv run --locked coverage combine

if [ -n "$check" ]; then
  uv run --locked coverage report -m --include="$check/*"
else
  bash tooling/coverage-population.sh
  uv run --locked coverage report -m
fi
