# check-eol

Fails if any file git treats as text has a CRLF line ending, anywhere in the tracked tree.
`.gitattributes` decides which files git treats as text.

An untracked, non-ignored file is invisible to the search, so it is reported as unsearchable rather
than silently unsearched — visibility fails it, not content. Both findings (an untracked file, a
CRLF match) accumulate in one run rather than short-circuiting, so an untracked file beside a CRLF
defect is one visit, not two.

A CRLF blob forced into history via `hash-object`/`update-index`, bypassing the add-time filter, is
still caught after a fresh clone — the check is not made redundant by git's own normalisation.

**Run outside a repository, or where the search itself fails, and the check fails with the
underlying git exit status** rather than reporting a clean scan.
**A repository with no tracked file reports success** — an empty scan is not a search failure, and a
failed or unreadable population enumeration is not an empty population and must fail.

**What this does not catch: a file whose `.gitattributes` sets the `binary` attribute.** That
attribute both exempts the file from CRLF→LF normalisation when it is added *and* excludes it from
the search, so genuinely CRLF-terminated text commits and survives a fresh clone unseen. The LF
invariant holds for files git treats as text, and `.gitattributes` decides which those are.

## Run locally

Install the distribution as described in [`../README.md`](../README.md) § Consuming a check, then
run it from the repository root:

```sh
uv run --locked check-eol
```

No arguments and no environment variables. The check reads `GITHUB_ACTIONS` itself to decide
whether to annotate a finding (`::error::`) or print it plainly; neither form changes the outcome.
