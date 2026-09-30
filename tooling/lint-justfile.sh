#!/usr/bin/env bash
# Every justfile recipe is a single line calling a script — no shebang recipe, no multi-line body
# — so what CI runs and what a human reads in the justfile are the same thing
# (docs/TESTING.md § Running tests locally). Run from the repository root, with `just` on PATH.
set -euo pipefail

bad="$(just --dump --dump-format json | jq -r '.recipes[] | select(.shebang or (.body | length) > 1) | .name')"

if [ -n "$bad" ]; then
  echo "recipe body is not a single line:"
  echo "$bad"
  exit 1
fi
