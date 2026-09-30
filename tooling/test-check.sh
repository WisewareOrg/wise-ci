#!/usr/bin/env bash
# Runs one check's tests under coverage, producing its raw (uncombined) coverage data files.
# Shared between check-eol.yml's own test job and `just test` (docs/TESTING.md § In CI). Run from
# the repository root, with the check's folder name as the one argument.
set -euo pipefail

check="$1"
uv run --locked coverage run -m pytest "$check/tests"
