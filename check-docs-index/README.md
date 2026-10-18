# check-docs-index

Fails unless every tracked Markdown file outside a top-level dot-directory is claimed by a row in
`docs/README.md`'s index table — the rule wise-ci's own [`docs/README.md`](../docs/README.md)
states for itself.

Run from the root of the repository it checks. It takes no inputs: `docs/README.md` is the only path
it reads by name.

## What it reports

Every finding accumulates into one run rather than short-circuiting, and the run fails if there is
any:

- a tracked Markdown file with no row, other than `docs/README.md` itself and anything under a
  top-level dot-directory;
- an untracked, non-ignored Markdown file, anywhere, dot-directories included — it is outside the
  population the check reads, so it is reported as unreadable rather than passed unread;
- a table row whose cell count is not three, or whose *Document* cell is not a link whose text is a
  backticked path;
- an empty *Guarantees* or *Excludes* cell;
- a row whose link target is not a tracked Markdown file;
- two rows rendering the same path;
- a row rendering a path that begins with `.` and holds a `/` — one under a top-level
  dot-directory, or one climbing out of the repository, which reads the same way;
- a row rendering a file path that is not a tracked Markdown file, or a directory path (one ending in
  `/`) holding no tracked Markdown file;
- no table row parsed at all, or no tracked Markdown file at all — the two inputs are sourced
  independently, so a parse that stops matching cannot report an empty index over an empty
  population as success.

A row rendering a path with a trailing slash claims every tracked Markdown file beneath it, at any
depth. Paths in the table are written relative to `docs/`.

On success it prints the row count and the count of tracked Markdown files — machinery and the
index included — and **names every top-level dot-directory it skipped as machinery**. Run outside a
git repository, it fails on the first git call: git's own message is captured, so what is printed is
the traceback naming the failed command.

## Known rejections

Legal Markdown the check refuses. Each fails closed, so none lets a defect through; each constrains
how `docs/README.md` may be written.

| Input | Reported as |
|---|---|
| GFM alignment delimiters in the separator row | the delimiter read as a *Document* cell, which is not a backticked-path link |
| a second Markdown table anywhere in the file | `a row has 2 cells, expected Document, Guarantees, Excludes` |
| a fenced table example — a code fence is not skipped | `a row has 2 cells, …` |
| the table indented one to three spaces, which still renders | `no index row parsed — the table's shape has moved` |
| a *Document* cell whose link text carries no backticks | the cell read as not a backticked-path link |
| an escaped pipe inside any cell | `a row has 4 cells, …` |

So `docs/README.md` holds exactly one table and no fenced example containing one: every `|`-leading
line is read as an index row.

## What this does not catch

**A new top-level dot-directory is machinery the moment it exists**, with no edit anywhere. The
machinery line on every passing run is what makes it visible: a directory appearing there without a
row in the index is the whole of what this rule lets through unremarked.

**A row can name only Markdown.** The tracked set a row's link and rendered path are compared against
is `git ls-files '*.md'`, so a row for a tracked file of any other kind is reported as naming nothing
tracked.

**Whether a row's cells are true** — that a document holds what its *Guarantees* cell says, and none
of what its *Excludes* cell says — is a reviewer's judgement, not this check's.
