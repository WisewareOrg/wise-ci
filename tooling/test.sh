#!/usr/bin/env bash
# `just test`'s own body: every check's tests with merged coverage, or one check's if given a
# folder name. Quiet on success (one line); full pytest/coverage output on failure. Calls the same
# scripts CI calls directly (docs/TESTING.md § In CI), so local and CI run identical logic. Run
# from the repository root.
set -euo pipefail

check="${1:-}"

if [ -n "$check" ]; then
  checks=("$check")
else
  checks=()
  for dir in */; do
    dir="${dir%/}"
    [ -f "$dir/action.yml" ] && checks+=("$dir")
  done
fi

log="$(mktemp)"
trap 'rm -f "$log"' EXIT

rm -f .coverage .coverage.*
status=0
for c in "${checks[@]}"; do
  bash tooling/test-check.sh "$c" >>"$log" 2>&1 || status=1
done

if [ "$status" -eq 0 ] && ! bash tooling/coverage-report.sh "$check" >>"$log" 2>&1; then
  status=1
fi

if [ "$status" -ne 0 ]; then
  cat "$log"
  exit 1
fi

if [ -n "$check" ]; then
  echo "test $check: passed, 100% coverage."
else
  echo "test (every check): passed, 100% coverage."
fi
