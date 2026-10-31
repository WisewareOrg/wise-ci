"""Two checks over docs/decisions/, run one after the other by main():

- index_check(): the docs/decisions/ directory and its index table agree -- every ADR file has a
  row, every row resolves to a real file, and numbering is contiguous from 0001 with no
  duplicates.
- revs_check(): every citation of an ADR, anywhere in the tracked tree, pins that ADR's current
  rev.

See check-adrs/README.md.

An ADR is a versioned document (`docs/decisions/README.md`): merged text is revisable, and a
correction is a new rev. A citation names the rev it was written against, so revving an ADR reaches
every document citing it — each is then updated or re-decided rather than left asserting a claim the
ADR's current rev does not make.

Assertions. The ADR set is read from `docs/decisions/` itself, so an uncommitted file is judged; the
citation scan reads the tracked set, and fails on any untracked, non-ignored path it therefore
cannot scan:

- Each ADR's head carries `**Rev:** N`, and the index table in `docs/decisions/README.md` agrees
  with it. The head is authoritative; the table is checked against it, never trusted.
- Each ADR's title line carries the number its filename carries. Identity by number is the premise
  every citation here rests on, and the head is where the document states it — the same head, one
  field over from the rev. Only the number is compared: the separator and the title text are the
  author's, and a rule reaching them would be a formatting gate.
- Every entry in `docs/decisions/` is an ADR this judges or a reported problem. One misnamed by case,
  separator or digit count carries no readable number, and passing over it reports a population
  smaller than the directory. The directory read above is what lets this see an entry no commit has
  yet introduced.
- Each ADR's *Revisions* section carries one changelog line per rev, numbered 1 to that head rev.
- No two files carry one number. Uniqueness is `index_check()`'s to enforce; it is reported here
  because a number two documents carry has no one rev to hold a citation of it to.
- Every `ADR NNNN` in prose is followed by `rev M`, and M is that ADR's current rev.
- Every markdown link resolving to an ADR file is titled `ADR NNNN rev M` likewise. The link rule is
  what the prose rule cannot reach: a citation spelled `[NNNN](NNNN-slug.md)` names no ADR in prose
  at all.
- A citation spelled in any other way — a plural, a hyphen, the wrong case, a reference-style link, a
  raw `<a href>` — is reported as malformed rather than passed over. The set this recognises is the
  set it can hold to a rev, so anything outside it must fail rather than shrink the population.

That an ADR's rev was raised for a good reason, and that a citation pinning the current rev still
means what the ADR says, is decided by nothing here.

Whether every index row has a file, and numbering is contiguous, is `index_check()`'s.
An ADR carrying no row is reported here as well, because the table assertion above is then the thing
with nothing to compare. It is not that such an ADR goes unjudged: the rev is read from the head, so
the title, changelog, collision and citation rules all still hold it, and deleting the table check
would change no citation verdict.

The repository is the working directory: an action's script runs from the consumer's checkout.
"""

import os
import re
import subprocess
import sys
from pathlib import Path


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


def index_check() -> int:
    root = Path.cwd()
    decisions_dir = root / "docs" / "decisions"

    problems = []

    files = {}
    for name in sorted(os.listdir(decisions_dir)):
        if name in ("README.md", "TEMPLATE.md") or not name.endswith(".md"):
            continue
        match = re.fullmatch(r"(\d{4})-.+\.md", name)
        if not match:
            problems.append(f"docs/decisions/{name} is not named NNNN-<slug>.md")
            continue
        # os.listdir reports names, not what they are: a directory or a dangling symlink named
        # NNNN-<slug>.md otherwise counts as an ADR on the strength of its name alone.
        if not (decisions_dir / name).is_file():
            problems.append(f"docs/decisions/{name} is not a readable file")
            continue
        if match.group(1) in files:
            problems.append(
                f"number {match.group(1)} is carried by two files: {files[match.group(1)]}, {name}"
            )
        else:
            files[match.group(1)] = name

    index_text = (decisions_dir / "README.md").read_text(encoding="utf-8")

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
        return 1
    print(f"decisions/ and its index agree: {len(files)} ADR(s), contiguous from 0001.")
    return 0


ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
HEAD_REV = re.compile(r"^\*\*Rev:\*\* *(\d+) *$", re.M)
# Read from the first non-blank line, and no further, so a fenced `# …` in the body cannot stand in
# for a missing title.
HEAD_TITLE = re.compile(r"^# +(\S+)")
NOT_AN_ADR = ("README.md", "TEMPLATE.md")
INDEX_ROW = re.compile(r"^(\| *\[\d{4}\]\([^)]+\) *\|)(.*)$")

# Any spelling that reaches for an ADR by number, deliberately wider than the one form accepted:
# separator, case, plural and digit count are all matched so they can be *reported*. Canonical form
# is then checked against the match text, so everything this recognises and does not accept fails.
CITATION = re.compile(r"\bADRs?[ _#\-]{0,3}(\d{1,4})\b(?: +rev +(\d+))?", re.I)
CANONICAL = re.compile(r"^ADR \d{4}(?: rev \d+)?$")

# Anchored on the target, never on the title: a title is arbitrary text and may carry brackets, so a
# title-shaped pattern is what a link to an ADR escapes through.
TARGET = re.compile(r"\]\(([^)\s]+)[^)]*\)")
LINK_TITLE = re.compile(r"^ADR ?(\d{4}) +rev +(\d+)$")
# Forms this cannot hold to a rev; each is reported if it targets an ADR.
REF_DEF = re.compile(r"^\[[^\]]+\]:\s*(\S+)")
RAW_HREF = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"']", re.I)

SECTION = re.compile(r"^## +(.+?) *$")
CHANGELOG = re.compile(r"^- \*\*rev (\d+)\*\* — ")
CONTINUATION = re.compile(r"^ {2,}\S")


def fail(problems):
    print(f"{len(problems)} problem(s):", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


def tracked(root):
    """Every tracked path, from git rather than a walk — the set CI is asked to judge."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
    ).stdout
    return [root / name.decode() for name in listing.split(b"\0") if name]


def untracked(root):
    """Untracked, non-ignored paths — outside the citation scan's population, so reported rather
    than silently unscanned."""
    listing = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    ).stdout
    return [name.decode() for name in listing.split(b"\0") if name]


def adr_links(line):
    """Every link on the line whose target is an ADR file, as (title, span, filename).

    The title is recovered by walking back from the closing `]` to its matching `[`, counting
    nesting, so a bracketed title is read rather than missed. A title that cannot be resolved yields
    `None` and is reported: an unreadable link to an ADR must fail, not be passed over.
    """
    for match in TARGET.finditer(line):
        name = match.group(1).split("#")[0].split("/")[-1]
        if not ADR_FILE.match(name):
            continue
        depth, start = 0, None
        for index in range(match.start(), -1, -1):
            if line[index] == "]":
                depth += 1
            elif line[index] == "[":
                depth -= 1
                if depth == 0:
                    start = index
                    break
        if start is None:
            yield None, range(0), name
        else:
            yield line[start + 1 : match.start()], range(start + 1, match.start()), name


def changelog_revs(text):
    """The rev numbers a document's *Revisions* section declares."""
    found, inside = [], False
    for line in text.split("\n"):
        heading = SECTION.match(line)
        if heading:
            inside = heading.group(1) == "Revisions"
            continue
        if inside:
            entry = CHANGELOG.match(line)
            if entry:
                found.append(int(entry.group(1)))
    return found


def current_revs(decisions, problems):
    """Each ADR's number and the rev its own head declares, and the numbers carried by two files."""
    revs, carriers, collided = {}, {}, set()
    for path in sorted(decisions.iterdir()):
        match = ADR_FILE.match(path.name)
        if not match:
            if path.name not in NOT_AN_ADR:
                problems.append(
                    f"docs/decisions/{path.name} is not named `NNNN-<lowercase-slug>.md`, so no "
                    "number can be read from it and nothing here judged it"
                )
            continue
        # An entry named like an ADR that is a directory or a dangling symlink is not one, and must
        # not pass for want of a readable head.
        if not path.is_file():
            problems.append(f"docs/decisions/{path.name} is not a readable file")
            continue
        # `utf-8-sig` drops a byte-order mark if one is there, so it cannot be read as part of the
        # title's number. Spelling that as a strip of the character itself puts an invisible one in
        # this source, where its loss would show up nowhere.
        text = path.read_text(encoding="utf-8-sig")
        title = HEAD_TITLE.match(next((l for l in text.splitlines() if l.strip()), ""))
        if not title:
            problems.append(
                f"docs/decisions/{path.name} opens with no `# NNNN …` line, so the document does "
                "not say which ADR it is"
            )
        elif title.group(1) != match.group(1):
            problems.append(
                f"docs/decisions/{path.name} titles itself {title.group(1)}, but its filename and "
                f"every citation of it say {match.group(1)}"
            )
        heads = HEAD_REV.findall(text)
        if len(heads) != 1:
            problems.append(
                f"docs/decisions/{path.name} declares {len(heads)} `**Rev:** N` lines, expected 1"
            )
            continue
        rev, number = int(heads[0]), match.group(1)
        # A number two files carry is dropped from the mapping rather than assigned from one of
        # them: which document it names is what a citation of it cannot be judged without, and
        # either assignment judges every such citation against a file chosen by sort order.
        if number in carriers:
            problems.append(
                f"docs/decisions/{carriers[number]} and docs/decisions/{path.name} both carry "
                f"number {number} — no rev can be attributed to it, so no citation of it is judged"
            )
            collided.add(number)
            revs.pop(number, None)
        else:
            carriers[number] = path.name
            revs[number] = rev
        declared = changelog_revs(text)
        if sorted(declared) != list(range(1, rev + 1)):
            problems.append(
                f"docs/decisions/{path.name} is at rev {rev} but its Revisions section declares "
                f"{declared or 'nothing'}, expected one line per rev from 1"
            )
    # Guarded on the heads that parsed, not on the mapping: a tree whose every number collided
    # empties `revs` while the format is fine, and would otherwise be reported as a parser fault.
    if not carriers:
        problems.append("no ADR declared a rev — the head format or this parser is wrong")
    return revs, collided


def check_index(index, revs, problems):
    """The index table's rev column repeats the head, and is checked against it."""
    rows = {}
    for line in index.read_text(encoding="utf-8").split("\n"):
        row = INDEX_ROW.match(line)
        if row:
            number = re.search(r"\[(\d{4})\]", row.group(1)).group(1)
            rows[number] = row.group(2).split("|")[0].strip()
    for number, rev in sorted(revs.items()):
        if number not in rows:
            problems.append(f"ADR {number} rev {rev} has no row in docs/decisions/README.md")
        elif not rows[number].isdigit():
            problems.append(
                f"docs/decisions/README.md row {number} has rev cell {rows[number]!r}, not a number"
            )
        elif int(rows[number]) != rev:
            problems.append(
                f"docs/decisions/README.md row {number} says rev {rows[number]}, "
                f"its head says rev {rev}"
            )


def readable(path, text, decisions, index):
    """The text of each line to judge, with the two exemptions applied.

    A **changelog line**, and any indented line continuing it, records what a rev did at the moment
    it did it — so a citation there is exempt from being *current*, and from nothing else. It must
    still be spelled canonically and still carry a rev; only the comparison against the ADR's head is
    dropped. An ordinary sentence in a *Revisions* section is a continuation of nothing and is judged
    like any other line, which is what stops the section being the place a stale citation is parked.

    An **index row** names its own document in its leading self-link, whose title is a bare number by
    construction. Only that link is dropped; the row's *Decision* cell is free prose and is judged.
    """
    in_revisions, in_entry = False, False
    for number, line in enumerate(text.split("\n"), start=1):
        heading = SECTION.match(line)
        if heading:
            in_revisions, in_entry = heading.group(1) == "Revisions", False
            yield number, line, False
            continue
        if in_revisions and path.parent == decisions:
            if CHANGELOG.match(line):
                in_entry = True
                yield number, line, True
                continue
            if in_entry and CONTINUATION.match(line):
                yield number, line, True
                continue
            in_entry = False
        row = INDEX_ROW.match(line) if path == index else None
        yield number, row.group(2) if row else line, False


def check_citations(root, decisions, index, revs, collided, problems):
    unreadable, judged = [], {"prose": 0, "link": 0}
    for path in tracked(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Not a skip the count hides: a file whose bytes are not text cannot carry a citation in
            # the form the rule defines, and every one of them is named on the way past.
            unreadable.append(path.relative_to(root))
            continue
        except OSError as error:
            problems.append(f"{path.relative_to(root)}: {error}")
            continue

        where = str(path.relative_to(root))
        for number, line, historical in readable(path, text, decisions, index):
            titles = []
            for title, span, name in adr_links(line):
                match = ADR_FILE.match(name)
                titles.append(span)
                judged["link"] += 1
                if title is None:
                    problems.append(
                        f"{where}:{number}: link to {name} has no title this can read — "
                        f"expected `[ADR {match.group(1)} rev N](...)`"
                    )
                    continue
                titled = LINK_TITLE.match(title.strip())
                if not titled:
                    problems.append(
                        f"{where}:{number}: link to {name} is titled {title!r}, "
                        f"expected `ADR {match.group(1)} rev N`"
                    )
                elif titled.group(1) != match.group(1):
                    problems.append(
                        f"{where}:{number}: link titled ADR {titled.group(1)} targets {name}"
                    )
                else:
                    problems.extend(
                        judge(revs, collided, where, number, titled.group(1),
                              titled.group(2), title, historical)
                    )

            for form, pattern in (("reference-style link", REF_DEF), ("raw <a href>", RAW_HREF)):
                for target in pattern.findall(line):
                    if ADR_FILE.match(target.split("#")[0].split("/")[-1]):
                        judged["link"] += 1
                        problems.append(
                            f"{where}:{number}: cites an ADR as a {form}, which carries no rev — "
                            f"write it inline as `[ADR NNNN rev M](...)`"
                        )

            for match in CITATION.finditer(line):
                # A title already judged above; judging it again would report one defect twice.
                # By position, not by text: a bare `ADR NNNN` is a substring of the title
                # `ADR NNNN rev M`, so a textual test suppresses the unpinned citation beside a
                # correctly titled link — a defect reported as none.
                if any(match.start() in span for span in titles):
                    continue
                judged["prose"] += 1
                spelling = match.group(0).split(" rev ")[0]
                if not CANONICAL.match(match.group(0)):
                    problems.append(
                        f"{where}:{number}: {spelling!r} is not a citation this can pin — "
                        f"write `ADR {match.group(1).zfill(4)} rev N`"
                    )
                    continue
                problems.extend(
                    judge(revs, collided, where, number, match.group(1), match.group(2),
                          line.strip(), historical)
                )

    if unreadable:
        print(
            f"not scanned, not decodable as text: {', '.join(map(str, unreadable))}",
            file=sys.stderr,
        )
    # The mirror of the guard in current_revs, and per mechanism rather than over the total: the
    # tree exercises both, so either falling to zero means that reader stopped seeing its citations
    # while the other kept the run green.
    for mechanism, count in judged.items():
        if not count:
            problems.append(
                f"no {mechanism} citation was judged — that spelling or this parser is wrong"
            )
    return sum(judged.values())


def judge(revs, collided, where, number, cited, pinned, context, historical=False):
    """One citation against the ADR it names.

    `historical` drops the comparison against the ADR's current rev, and drops nothing else: a
    changelog entry may name a rev that has moved on, but not an ADR that does not exist and not a
    citation carrying no rev at all.

    A citation of a colliding number is left unjudged, and the run fails on the collision itself.
    Judging it reports a rev disagreement the tree does not have, against a correct citation, and
    the repair that reads as obvious — move the pin — writes a wrong rev across the tree.
    """
    if cited in collided:
        return []
    if cited not in revs:
        return [f"{where}:{number}: cites ADR {cited}, which is not an ADR — {context}"]
    if not pinned:
        return [f"{where}:{number}: cites ADR {cited} without a rev — {context}"]
    if historical:
        return []
    if int(pinned) != revs[cited]:
        return [f"{where}:{number}: pins ADR {cited} rev {pinned}, current is rev {revs[cited]}"]
    return []


def revs_check() -> int:
    root = Path.cwd()
    decisions = root / "docs" / "decisions"
    index = decisions / "README.md"

    problems = [
        f"{name}: untracked, so the citation scan cannot read it — git add or gitignore it"
        for name in untracked(root)
    ]
    revs, collided = current_revs(decisions, problems)
    judged = 0
    if revs:
        check_index(index, revs, problems)
        judged = check_citations(root, decisions, index, revs, collided, problems)
    if problems:
        return fail(sorted(problems))
    print(f"{len(revs)} ADRs; {judged} citations, every one pinning the current rev")
    return 0


def main() -> int:
    index_result = index_check()
    revs_result = revs_check()
    return 1 if index_result or revs_result else 0
