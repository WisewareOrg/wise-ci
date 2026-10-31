# check-adrs

One console script running two halves, as one Actions step: the index half fails unless
`docs/decisions/` and its index table in `docs/decisions/README.md` agree; the revs half fails
unless every citation of an ADR, anywhere in the tracked tree, pins that ADR's current rev. The
revs half always runs, even if the index half failed or crashed; the check exits 1 if either half
failed, and prints nothing of its own beyond each half's own output.

Run from the root of the repository it checks. It takes no inputs: `docs/decisions/` and the
tracked tree are the only paths either half reads by name.

## What the index half ([`check_adrs/check_adr_index.py`](check_adrs/check_adr_index.py)) reports

Read from `docs/decisions/`'s own directory listing, not git's tracked set — an ADR file the
listing reports is judged whether or not it has been `git add`ed. `README.md` and `TEMPLATE.md` are
skipped by name; every other `.md` entry is judged:

- a `.md` entry not named `NNNN-<slug>.md`;
- an entry named like an ADR that is a directory or a dangling symlink, so it carries no readable
  file;
- two files carrying one number;
- an ADR file with no row in `docs/decisions/README.md`'s index table, and a row naming no ADR
  file;
- two rows for one number, and a row linking the wrong filename for its number;
- numbering not contiguous from `0001`.

A row's link target may carry a title, be angle-bracketed, lead with `./`, or end in a `#anchor`;
none of that is part of the filename the row claims. Only `docs/decisions/README.md` is read — a
row-shaped line in another file, or one indented so it no longer opens the line, is not a row at
all.

On success it prints the ADR count. A git call is never made: a missing `docs/decisions/`
directory, or a missing `docs/decisions/README.md` within one that exists, fails: the exception
propagates out of the index half, and the packaged script reprints its traceback (the same text
Python prints for one left uncaught), naming the missing path, rather than a reported problem.

## What the revs half ([`check_adrs/check_adr_revs.py`](check_adrs/check_adr_revs.py)) reports

The ADR set is read from `docs/decisions/` directly, the same as the index half, so an uncommitted
ADR is judged; the citation scan reads the tracked set instead (`git ls-files`), and fails outright
on any untracked, non-ignored path — it is outside what the scan can read, and is reported rather
than silently unscanned. Every other finding accumulates into one run:

- an ADR entry not named `NNNN-<lowercase-slug>.md`, one that is a directory or dangling symlink, or
  one with no `**Rev:** N` head line (or more than one);
- an ADR's title line naming a different number than its filename, or no title line at all;
- two files carrying one number — the citation of a colliding number is then left unjudged, since no
  one file owns its rev; the run still fails, on the collision itself;
- an ADR's *Revisions* section not declaring exactly one line per rev from 1 to its head's rev;
- the index table's rev column disagreeing with an ADR's head, naming no row for an ADR, or holding
  a non-numeric rev cell;
- a prose citation (`ADR NNNN`) with no `rev M`, or pinning a rev that is not current;
- a markdown link to an ADR file whose title cannot be read as `ADR NNNN rev M`, or whose title names
  a different ADR than the link targets;
- an ADR cited as a reference-style link or a raw `<a href>`, neither of which can carry a title to
  pin a rev to;
- a citation spelled with a plural, a hyphen, an underscore, a hash, a doubled space, the wrong
  case, or too few digits — recognised deliberately wider than the one accepted form, so each is
  reported rather than passed over.

**A changelog line is exempt from currency, not from form.** A line in a *Revisions* section
matching `- **rev N** — `, and an indented line continuing it, may cite a rev that is no longer
current — recording what a rev did at the moment it did it — but must still be spelled canonically
and still carry a rev. An ordinary, unindented sentence in a *Revisions* section gets no exemption.
An index row's own leading self-link is dropped before scanning; its *Decision* cell is free prose
and is judged like any other.

A tracked file this cannot decode as text is named and skipped, not failed on by itself. On success
it prints the ADR count and the citation count, split by whether each was judged a prose or a link
citation — and fails if either count is zero, since a scan that stops recognising a whole citation
form would otherwise report the smaller population it can still see as complete.

A missing `docs/decisions/` directory fails the same way the index half's own missing directory
does: the exception propagates out of the revs half, and the packaged script reprints its
traceback, naming it. A missing `docs/decisions/README.md` fails the same way, but only once at
least one ADR has validated — with none, there is nothing to check the index against, and the run
instead reports `no ADR declared a rev` as an ordinary problem.

## Known rejections

Legal input each half refuses. Each fails closed, so neither lets a defect through:

| Half | Input | Reported as |
|---|---|---|
| index | a row inside a fenced code block | a real row — there is no fence blanking, so `docs/decisions/README.md` may not carry a fenced example table |
| revs | an illustrative example spelling a live ADR number | a stale citation — write an example as `NNNN`, never a real number |

## What this does not catch

**The index half's `.md` match is case-sensitive.** An ADR file named with an uppercase extension
is invisible to the directory scan rather than rejected by the naming rule.

**Only ADRs, the index and the template may live in `docs/decisions/`.** The revs half reports
every other entry — a subdirectory, a non-Markdown asset, a dotfile — as unreadable-numbered, which
narrows what the directory may hold; the index half reports only entries matching the ADR naming
pattern, so a stray without that shape passes it unseen. An untracked stray fails the revs half's
untracked guard either way.

**An H1 indented up to three spaces is legal CommonMark and is rejected.** The revs half matches an
ADR's title from the first character of the first non-blank line; an indented opening line is read
as carrying no title at all.

**A title number is read as a token, not a number.** The revs half takes the first
whitespace-delimited token after `# ` as the title's number; a title running the number into its
text is reported as titling itself that whole token, not as separately malformed.

**A citation split by a line wrap right after `ADR` or `rev` is invisible.** The revs half matches a
citation within one line; a line ending in the bare keyword and the next opening with the number or
the rev carries the citation across neither line, so the pin goes unchecked until the lines are
joined.

## Run locally

Install the distribution as described in [`../README.md`](../README.md) § Consuming a check, then
run it from the root of the repository it checks:

```sh
uv run --locked check-adrs
```

No arguments and no environment variables.
