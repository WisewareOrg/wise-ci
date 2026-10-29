#!/usr/bin/env python3
"""The docs/decisions/ directory and its index table agree: every ADR file has a
row, every row resolves to a real file, and numbering is contiguous from 0001
with no duplicates. See check-adrs/README.md.

No dependencies: Python stdlib only, plain text scanning.

The repository is the working directory: an action's script runs from the consumer's checkout.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
DECISIONS_DIR = ROOT / "docs" / "decisions"

problems = []

files = {}
for name in sorted(os.listdir(DECISIONS_DIR)):
    if name in ("README.md", "TEMPLATE.md") or not name.endswith(".md"):
        continue
    match = re.fullmatch(r"(\d{4})-.+\.md", name)
    if not match:
        problems.append(f"docs/decisions/{name} is not named NNNN-<slug>.md")
        continue
    # os.listdir reports names, not what they are: a directory or a dangling symlink named
    # NNNN-<slug>.md otherwise counts as an ADR on the strength of its name alone.
    if not (DECISIONS_DIR / name).is_file():
        problems.append(f"docs/decisions/{name} is not a readable file")
        continue
    if match.group(1) in files:
        problems.append(
            f"number {match.group(1)} is carried by two files: {files[match.group(1)]}, {name}"
        )
    else:
        files[match.group(1)] = name

index_text = (DECISIONS_DIR / "README.md").read_text(encoding="utf-8")


def destination(value):
    """A destination may be angle-bracketed, carry a title, lead with ./ or end in an anchor; none
    of that is part of the filename the row is claiming."""
    raw = value.strip()
    titled = re.match(r"(\S+)\s+[\"'(]", raw)
    if titled:
        raw = titled.group(1)
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1]
    raw = raw.split("#")[0]
    return raw[2:] if raw.startswith("./") else raw


rows = {}
for match in re.finditer(r"^\|\s*\[(\d{4})\]\(([^)]+)\)\s*\|", index_text, flags=re.M):
    number, raw_target = match.group(1), match.group(2)
    target = destination(raw_target)
    if number in rows:
        problems.append(f"docs/decisions/README.md has two rows for number {number}")
    else:
        rows[number] = target

for number, name in files.items():
    if number not in rows:
        problems.append(f"docs/decisions/{name} has no row in docs/decisions/README.md")
for number, target in rows.items():
    if number not in files:
        problems.append(f"docs/decisions/README.md row {number} names no ADR file")
    elif target != files[number]:
        problems.append(
            f"docs/decisions/README.md row {number} links '{target}', but the file is '{files[number]}'"
        )

for index, number in enumerate(sorted(files)):
    expected = str(index + 1).zfill(4)
    if number != expected:
        problems.append(
            f"ADR numbering is not contiguous from 0001: expected {expected}, found {number}"
        )

if problems:
    print(
        f"check-adr-index: the decisions directory and its index disagree ({len(problems)}):",
        file=sys.stderr,
    )
    for problem in problems:
        print("  " + problem, file=sys.stderr)
    sys.exit(1)
print(f"decisions/ and its index agree: {len(files)} ADR(s), contiguous from 0001.")
