# 0002 — The documentation index claims every tracked document, derived from the repository

**Status:** accepted
**Decided:** 2026-10-18 (wise-ci issue 49 owner rulings)
**Rev:** 1

## Revisions

- **rev 1** — 2026-10-18 — first written (#49 migrate check-docs-index to wise-ci).

## Context

[`../README.md`](../README.md) states that every fact about wise-ci has exactly one canonical home,
and that *"every tracked document is claimed by a row here unless it sits under a top-level
dot-directory"*. Nothing enforced it: a document could be added and indexed nowhere, or retired while
its row stood, and every check passed. The index also carried two placeholder rows, `<check>/README.md`
and `<check>/action.yml`, each standing for a family of files rather than naming one.

Enforcing the rule means deciding what counts as claiming a document, where the set of documents comes
from, and what is excluded from it and on whose say-so.

## Decision

**A row in the documentation index claims a document.** A tracked Markdown file is claimed by a row in
[`../README.md`](../README.md)'s table, or it is machinery under a top-level dot-directory. Nothing
else claims a document.

**The claimable set is derived from the repository.** `git ls-files '*.md'` is the population, so a
document added without a row fails. No inventory of documents is maintained by hand.

**A row's own cell says what it claims**, so the check reads a signal the table already carries rather
than adding syntax: a *Document* cell whose text is a path (`CI.md`) claims that one file, and one
whose text ends in a slash (`decisions/`) claims every tracked Markdown file beneath it.

**What is not a document is derived too.** A tracked Markdown file under a **top-level
dot-directory** is machinery — an agent's working material, GitHub's own forms — and is claimed by
nothing. There is no exclusions list, so excluding anything else takes an edit to the check, reviewed
as code and needing a rev of this ADR, rather than a line anyone can append to a list.

Deriving both sides is the point. An inventory of documents and an inventory of exclusions are the
same artifact facing opposite directions, and a decision that rejects one while shipping the other
has only moved where the drift lives.

**The index's rows are unique and real.** One rendered path carries one row — two rows for a document
is two canonical homes, which is the property the index exists to state — and a row names a tracked
document, or a directory holding one. **A document map has no placeholder rows**: the
`<check>/README.md` row becomes one row per check's real `README.md`.

The check also asserts that it parsed the table at all. A pattern that silently stops matching would
otherwise leave every document unclaimed and report nothing, so the two inputs stay independently
sourced: `git ls-files` against the file.

## Alternatives considered

**A committed canonical-document list**, compared against the index table in both directions.
Rejected: it is a third artifact beside the table and the repository, and drifts from both — adding a
document while updating neither the list nor the table still passes, which is the failure the check
exists to catch. A hand-maintained inventory is a declaration, and a gate satisfied by declaring is a
checkbox.

**A committed exclusions list** naming the directories nothing indexes, one entry per line. Rejected:
a one-line edit to it hides a document — appending an entry over a directory whose row has just gone,
or over one nobody has indexed yet, which needs no row touched at all. Guarding the first case takes
rules of its own; the second is closed only by not having the list. The list's supposed advantage —
excluding a directory without touching code — is precisely the property that makes it an opt-out.

**Teaching the check a placeholder syntax**, so a row like `<check>/README.md` claims every file of
that shape. Rejected: a placeholder row names no file, so the uniqueness and reality guarantees above
cannot apply to it, and the check would carry a template grammar to serve one table. One row per real
file costs a row per check and keeps every row checkable.

## Consequences

Adding a document fails until it is indexed; retiring one fails until its row goes. That is the
obligation the index has always stated and never enforced. Adding a check adds a row for its
`README.md`.

**A new top-level dot-directory is excluded the moment it exists, with no edit anywhere.** This is the
one respect in which the derived rule is weaker than a list, which would have demanded a visible line
for it. Closing it would mean asserting which dot-directories may exist — the inventory this decision
exists to avoid. What makes it reviewable is that the check **names** the machinery directories it
skipped on every passing run: a directory appearing in that line without a row in the index is the
whole of what this rule lets through unremarked.

The cost of having no list is that a directory which is *not* a dot-directory — vendored
documentation, a `third_party/` tree — cannot be excluded without changing the check and revving this
ADR. That is the intended price.

The population is Markdown, so a row can name only a Markdown file or a directory holding one; a
check's `action.yml` has no row of its own.

The check reads rendered table structure, so reformatting the index — changing its columns, or moving
it off a Markdown table — breaks it, loudly rather than by reporting zero rows.
