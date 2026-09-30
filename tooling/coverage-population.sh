#!/usr/bin/env bash
# Fails, naming the files, if any check's source file is missing from the merged coverage data —
# independent of the coverage config that normally discovers them (pyproject.toml's source/omit/
# include_namespace_packages), so a narrowed check-job checkout or a narrowed coverage config
# fails loudly rather than dropping a check's source out of the report unnoticed
# (docs/TESTING.md § In CI). Run after `coverage combine`, from the repository root.
set -euo pipefail

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

for dir in */; do
  dir="${dir%/}"
  [ -f "$dir/action.yml" ] || continue
  find "$dir" -name '*.py' -not -path "$dir/tests/*"
done | sort > "$tmp/expected-py-files"

if [ ! -s "$tmp/expected-py-files" ]; then
  echo "no check's source files were found — run this from the repository root" >&2
  exit 1
fi

if ! grep -qxF "check-eol/check-eol.py" "$tmp/expected-py-files"; then
  echo "expected file list is missing check-eol/check-eol.py" >&2
  exit 1
fi

# --fail-under=0: pyproject.toml's own fail_under=100 would otherwise exit this command on an
# under-covered file before the missing-file comparison below ever runs, hiding the name this
# script exists to report. The 100% bar is the caller's job, after this script returns.
uv run --locked coverage json --fail-under=0 -o "$tmp/coverage.json"
jq -r '.files | keys[]' "$tmp/coverage.json" | sort > "$tmp/covered-py-files"

missing="$(comm -23 "$tmp/expected-py-files" "$tmp/covered-py-files")"
if [ -n "$missing" ]; then
  echo "missing from the merged coverage data:"
  echo "$missing"
  exit 1
fi
