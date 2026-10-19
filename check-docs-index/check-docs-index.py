#!/usr/bin/env python3
"""Every tracked Markdown file outside a top-level dot-directory is claimed by a row in
docs/README.md's index; one rendered path carries one row; a row names a tracked
document, or a directory holding one; every row's link resolves to a tracked file;
and no Guarantees or Excludes cell is empty. A row rendering with a trailing slash
claims the subtree beneath it. See check-docs-index/README.md.

No dependencies: Python stdlib only, plain text scanning.

The repository is the working directory: an action's script runs from the consumer's checkout.
"""

import posixpath
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
INDEX = "docs/README.md"

problems = []


def from_docs(path):
    """The index's links are written relative to docs/; this returns them repo-relative.

    A trailing slash is a subtree claim, and posixpath.normpath strips it, so it is put back.
    """
    joined = posixpath.join("docs", path)
    normalized = posixpath.normpath(joined)
    if joined.endswith("/") and not normalized.endswith("/"):
        normalized += "/"
    return normalized


tracked = {
    name
    for name in subprocess.run(
        ["git", "ls-files", "-z", "*.md"], cwd=ROOT, capture_output=True, check=True
    )
    .stdout.decode()
    .split("\0")
    if name
}

# Untracked Markdown is outside the population above, so it is reported rather than silently unread.
for name in (
    subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z", "*.md"],
        cwd=ROOT, capture_output=True, check=True,
    )
    .stdout.decode()
    .split("\0")
):
    if name:
        problems.append(f"{name}: untracked, so this check cannot read it — git add or gitignore it")

file_claims = set()
subtree_claims = []
claimed = set()
rows = 0

for line in (ROOT / INDEX).read_text(encoding="utf-8").split("\n"):
    if not line.startswith("|"):
        continue
    cells = [cell.strip() for cell in line.split("|")[1:-1]]
    if (cells and cells[0] == "Document") or all(re.fullmatch(r"-+", cell) for cell in cells):
        continue
    if len(cells) != 3:
        problems.append(
            f"{INDEX}: a row has {len(cells)} cells, expected Document, Guarantees, Excludes"
        )
        continue

    document, guarantees, excludes = cells
    link = re.fullmatch(r"\[`([^`]+)`\]\(([^)]+)\)", document)
    if not link:
        problems.append(f"{INDEX}: Document cell '{document}' is not a backticked-path link")
        continue
    rows += 1

    rendered, target = link.group(1), link.group(2)
    if not guarantees:
        problems.append(f"{INDEX}: row '{rendered}' has an empty Guarantees cell")
    if not excludes:
        problems.append(f"{INDEX}: row '{rendered}' has an empty Excludes cell")

    linked = from_docs(target)
    if linked not in tracked:
        problems.append(f"{INDEX}: row '{rendered}' links '{target}', which is not a tracked file")

    claim = from_docs(rendered)
    if claim in claimed:
        problems.append(f"{INDEX}: '{rendered}' has two rows — one fact, one canonical home")
    claimed.add(claim)

    if claim.startswith(".") and "/" in claim:
        problems.append(f"{INDEX}: row '{rendered}' indexes a dot-directory, which is machinery")

    if rendered.endswith("/"):
        subtree_claims.append(claim)
        if not any(path.startswith(claim) for path in tracked):
            problems.append(
                f"{INDEX}: row '{rendered}' claims a directory holding no tracked document"
            )
    else:
        file_claims.add(claim)
        if claim not in tracked:
            problems.append(f"{INDEX}: row '{rendered}' names no tracked document")

# Independently sourced — the git index against the index file — so a parse that stops
# matching cannot take both to zero at once. See check-docs-index/README.md.
if not rows:
    problems.append(f"{INDEX}: no index row parsed — the table's shape has moved")
if not tracked:
    problems.append("git ls-files reported no tracked Markdown file")

machinery = set()
for path in sorted(tracked):
    if path == INDEX:
        continue  # The index does not index itself.
    if path.startswith(".") and "/" in path:
        machinery.add(path[: path.index("/") + 1])  # A top-level dot-directory holds machinery. docs/README.md.
        continue
    if path in file_claims:
        continue
    if any(path.startswith(subtree) for subtree in subtree_claims):
        continue
    problems.append(f"{path} has no row in {INDEX}")

if problems:
    print(
        f"check-docs-index: the documentation set and its index disagree ({len(problems)}):",
        file=sys.stderr,
    )
    for problem in problems:
        print("  " + problem, file=sys.stderr)
    sys.exit(1)
# Names every machinery directory skipped (check-docs-index/README.md § What this does not catch).
print(
    f"every tracked document is claimed: {rows} index row(s), {len(tracked)} document(s).\n"
    f"machinery, claimed by nothing: {' '.join(sorted(machinery)) or 'none'}"
)
