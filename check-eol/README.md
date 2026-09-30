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
