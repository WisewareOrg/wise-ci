"""Fails when a cited `SYS`/`SRS`/`TST` identifier, in tracked Markdown or an item's `rationale`
and `verification-justification`, names no item in the requirements tree, is mis-cased, or carries
no correctly-formed header comment.

Scope is resolution, the header pair, and the comment's placement. Whether a cited item is
accepted, and whether the sentence means the item it names, is beyond this.
"""

import re
import subprocess
import sys
from pathlib import Path

import doorstop

UID = re.compile(r"\b(?:SYS|SRS|TST)\d{3}\b")
# Found case-insensitively so a mis-cased identifier is judged rather than skipped: matching only
# the canonical spelling makes every other spelling invisible to the check rather than wrong.
UID_ANY_CASE = re.compile(r"\b(?:SYS|SRS|TST)\d{3}\b", re.IGNORECASE)
FENCE = re.compile(r"^\s*(?:```|~~~)")
QUOTE = re.compile(r"^\s*>\s?")


def in_git_working_copy() -> bool:
    """True when the working directory is inside a git working copy -- the precondition this
    stage's own `git ls-files` calls need before they can run without crashing."""
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def items():
    """Every item in the tree. Document.items skips inactive items; the whole TST tier is
    inactive."""
    cwd = str(Path.cwd())
    tree = doorstop.build(cwd=cwd, root=cwd)
    return [item for document in tree.documents for item in document._iter()]


def markdown_sources():
    """Tracked Markdown, less `.claude/` -- agent instructions cite the tree to describe how to
    work on it, and are not part of the documentation set."""
    cwd = Path.cwd()
    tracked = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.split()
    for name in tracked:
        if name.startswith(".claude/"):
            continue
        yield (name, *blank_fences((cwd / name).read_text()))


def untracked_markdown():
    """Untracked Markdown, less `.claude/` -- the population above cannot see it, so it is reported
    rather than silently unread. `-z` keeps a path with a space or non-ASCII bytes one name."""
    others = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z", "*.md"],
        cwd=Path.cwd(), capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    return [name for name in others if name and not name.startswith(".claude/")]


def blank_fences(text):
    """Fenced code blocks replaced by spaces of equal length, so offsets still name the right
    line."""
    out, fence = [], None
    for line in text.split("\n"):
        marker = FENCE.match(line)
        if fence is None and marker:
            fence = marker.group().strip()[0]
        elif fence is not None and marker and marker.group().strip()[0] == fence:
            fence = None
            out.append(" " * len(line))
            continue
        out.append(" " * len(line) if fence is not None else line)
    # A fence that never closes blanks the rest of the file, so every citation below it would go
    # unread. Reported rather than skipped.
    return "\n".join(out), fence is not None


def item_sources(tree_items):
    """Each item's explanatory fields, with the line their first content line sits on. An offset
    within a block-scalar value is an offset within the file; an offset within a short, plain-
    scalar value is not (check-reqs/README.md § Known gaps)."""
    cwd = Path.cwd()
    for item in tree_items:
        path = Path(item.path)
        lines = path.read_text().split("\n")
        for field in ("rationale", "verification-justification"):
            value = item.get(field) or ""
            if not value.strip():
                continue
            start = next(i for i, line in enumerate(lines) if line.startswith(f"{field}:"))
            yield path.relative_to(cwd).as_posix(), value, start + 2


def normalise(text):
    """One normaliser, applied to both sides of every comparison. A line break and the blockquote
    marker continuing it are whitespace between the identifier and its header, not text separating
    them; case and run length do not signify. Normalising the header the same way is what lets a
    header contain a character the surrounding markup also uses."""
    return " ".join(re.sub(r"\n[^\S\n]*>?", " ", text).split()).casefold()


def annotation(text):
    """The header a citation carries, and the form it was written in. The identifier's own closing
    backtick and possessive clitic may sit between the two; whitespace may not -- a space there
    outlives the comment into the rendered page as a gap before the following punctuation."""
    rest = re.sub(r"^(?:`|'s|')+", "", text)
    if rest.startswith("<!--"):
        end = rest.find("-->")
        return ("comment", rest[4:end]) if end != -1 else ("unterminated", "")
    if re.match(r"\s+<!--", rest):
        return ("loose", "")
    return ("missing", "")


def interrupting_comments(source, text):
    """Every comment opening a line that continues a paragraph, blockquote continuations
    included."""
    problems = []
    lines = [QUOTE.sub("", line) for line in text.split("\n")]
    for number, line in enumerate(lines[1:], start=2):
        if line.lstrip().startswith("<!--") and lines[number - 2].strip():
            problems.append(
                f"{source}:{number}  a comment opens this line, splitting the paragraph above it"
                f" — bind it to the text it follows, or leave a blank line before it"
            )
    return problems


def check(source, text, item_headers, base=1):
    problems = []
    for match in UID_ANY_CASE.finditer(text):
        uid = match.group()
        line = base + text.count("\n", 0, match.start())
        if uid != uid.upper():
            problems.append(
                f"{source}:{line}  {uid}  is not uppercase — an identifier is cited as {uid.upper()}"
            )
            continue
        if uid not in item_headers:
            problems.append(f"{source}:{line}  {uid}  names no item in the requirements tree")
            continue
        if text[match.end() :].startswith(".yml"):
            continue  # an item's own filename: it resolves, and names rather than cites the item
        expected = normalise(item_headers[uid])
        kind, carried = annotation(text[match.end() :])
        if kind == "loose":
            problems.append(
                f"{source}:{line}  {uid}  whitespace separates the identifier from its header"
                f" — close it up, or the gap renders as one before the punctuation that follows"
            )
        elif kind == "unterminated":
            problems.append(f"{source}:{line}  {uid}  opens a header comment that never closes")
        elif kind == "missing":
            problems.append(f"{source}:{line}  {uid}  carries no header comment")
        elif kind == "comment" and normalise(carried) != expected:
            problems.append(
                f"{source}:{line}  {uid}  expected the item's header '{item_headers[uid]}'"
                f", found '{normalise(carried)}'"
            )
    return problems


def main(root: Path) -> int:
    tree_items = items()
    item_headers = {str(item.uid): (item.header or "").strip() for item in tree_items}

    problems = []
    for name in untracked_markdown():
        problems.append(f"{name}  untracked, so this check cannot read it — `git add` or gitignore it")
    for name, text, unterminated in markdown_sources():
        if unterminated:
            problems.append(f"{name}  a code fence is never closed, so everything below it goes unread")
        problems += check(name, text, item_headers)
        problems += interrupting_comments(name, text)
    for path, value, base in item_sources(tree_items):
        problems += check(path, value, item_headers, base)

    if problems:
        print(f"{len(problems)} citation problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nA citation carries the identifier and the item's header verbatim, in an HTML comment"
            "\nclosed up to it: SRS015<!-- One schema, all boundary value classes -->. No whitespace"
            "\nat the junction, and the comment never opens a line that continues a paragraph.",
            file=sys.stderr,
        )
        return 1

    print("Every citation resolves, and every requirement citation carries its item's header.")
    return 0
