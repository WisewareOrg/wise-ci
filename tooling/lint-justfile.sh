#!/usr/bin/env bash
# Every justfile recipe is a single line calling a script — no shebang recipe, no multi-line body,
# and no chained command (&&, ||, ;) hiding a second one on that line — so what CI runs and what a
# human reads in the justfile are the same thing (docs/TESTING.md § Running tests locally). Run
# from the repository root, with `just` on PATH.
set -euo pipefail

recipes_json="$(just --dump --dump-format json)"

shaped="$(jq -r '.recipes[] | select(.shebang or (.body | length) > 1) | .name' <<<"$recipes_json")"
if [ -n "$shaped" ]; then
  echo "recipe body is not a single line:"
  echo "$shaped"
  exit 1
fi

# A single body line can still chain more than one command; reconstructed here as literal text
# (an interpolation becomes a placeholder that can't itself look like an operator) and checked
# with a real shell tokenizer, so a quoted `;` or `&&` in an argument isn't mistaken for one.
chained=""
while IFS=$'\t' read -r name line; do
  if python3 -c '
import shlex, sys
tokens = shlex.shlex(sys.argv[1], punctuation_chars=True)
tokens.whitespace_split = True
sys.exit(0 if any(t in ("&&", "||", ";") for t in tokens) else 1)
' "$line"; then
    chained="$chained$name"$'\n'
  fi
done < <(jq -r '.recipes[] | [.name, ([.body[0][]? | if type == "array" then "X" else . end] | join(""))] | @tsv' <<<"$recipes_json")

if [ -n "$chained" ]; then
  echo "recipe chains more than one command on its line:"
  printf '%s' "$chained"
  exit 1
fi
