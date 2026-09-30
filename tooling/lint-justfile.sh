#!/usr/bin/env bash
# Every justfile recipe, and every recipe in every module it includes, is either exactly
# `just --list`, or a single line calling `bash tooling/<name>.sh` with nothing but quote()-wrapped
# arguments after it — no shebang, no [script] attribute, no chained command (;, &&, ||, |), and no
# other command — so what CI runs and what a human reads in the justfile are the same thing
# (docs/TESTING.md § Running tests locally). Run from the repository root, with `just` on PATH.
set -euo pipefail

# namepath already carries a module's recipe as "module::recipe", so the failure list needs no
# extra qualification.
recipes="$(just --dump --dump-format json | jq -c '
  def all_recipes: (.recipes // {} | .[]), ((.modules // {} | .[]) | all_recipes);
  [all_recipes | {namepath, shebang, body}]
')"

# This is Python source, not shell; single quotes are what keep bash from touching it.
# shellcheck disable=SC2016
bad="$(python3 -c '
import json, re, sys

recipes = json.load(sys.stdin)
listed = (["just --list"], ["@just --list"])
head_re = re.compile(r"@?bash tooling/[\w.-]+\.sh( )?")

def is_quote_call(seg):
    return (
        isinstance(seg, list) and len(seg) == 1 and isinstance(seg[0], list)
        and len(seg[0]) >= 2 and seg[0][0] == "call" and seg[0][1] == "quote"
    )

for r in recipes:
    name = r["namepath"]
    if r["shebang"]:
        print(f"{name}: has a shebang, a [script] attribute, or is otherwise not a plain command")
        continue
    body = r["body"]
    if len(body) == 0:
        continue
    if len(body) > 1:
        print(f"{name}: body is more than one line")
        continue
    line = body[0]
    if line in listed:
        continue
    reason = "must call `bash tooling/<name>.sh` with nothing but quoted arguments after it"
    if not line or not isinstance(line[0], str):
        print(f"{name}: {reason}")
        continue
    m = head_re.fullmatch(line[0])
    if not m:
        print(f"{name}: {reason}")
        continue
    rest = line[1:]
    if rest and not m.group(1):
        print(f"{name}: {reason}")
        continue
    ok = True
    for i, seg in enumerate(rest):
        if i % 2 == 0:
            ok = is_quote_call(seg)
        else:
            ok = isinstance(seg, str) and seg.strip() == ""
        if not ok:
            break
    if not ok:
        print(f"{name}: {reason}")
' <<<"$recipes")"

if [ -n "$bad" ]; then
  echo "recipe does not call a script the way every justfile recipe must:"
  echo "$bad"
  exit 1
fi
