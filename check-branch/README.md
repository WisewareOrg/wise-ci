# check-branch

Enforces the branch-shape, ticket-linkage and epic-membership rules stated once in
[`WisewareOrg/.github`'s `PROCESS.md`](https://github.com/WisewareOrg/.github/blob/main/PROCESS.md)
(PROC-001, PROC-003 through PROC-008, and PROC-010). **This restates no requirement** — this
check is one of the gates that enforces them.

Runs only inside a pull request: outside one, the check fails closed rather than falling back to a
local lookup.

## Inputs

See [`action.yml`](action.yml) for each input's description and default. `branch` is overridable
for a workflow that needs to check a branch other than the triggering PR's own head.

`contents: read` is the only permission this needs on a public repository — every REST and GraphQL
call it makes reads data a public repository exposes to an unauthenticated or read-scoped token. A
private consumer additionally needs `issues: read` and `pull-requests: read`. See
[`../README.md`](../README.md) § Consuming a check for how to reference this action.

## History

**The branch types are built in, not a `types` input.** PROC-010 fixes the ticket-type set; a
consumer with a different set is not this check's case to generalise for. This also retires
`branch-shape.regex`'s file-based pattern, and with it the
generality that file carried: each of its non-blank lines was an independent alternative pattern, not
only a type-set list — nothing in `PROCESS.md` asks for that generality, and no input reintroduces
even the narrower form (a type-set substituted into one fixed pattern) that an earlier design for
this migration considered. That file's design needed two guards, not one: a name matching *some*
line proved only that *a* pattern matched, not that the type read out of it was the file's one
authoritative type group — a file whose lines disagreed on the type set could satisfy the first
guard while the second caught it. A single fixed pattern with one alternation has only the one
question this script asks.

**A branch's number can resolve to a pull request rather than an issue.** GitHub draws issues and
pull requests from one counter, so a branch named for a merged pull request's number is shape-valid
and resolves to a real object — of the wrong kind. PROC-003 rejects it on kind, not on existence.

**The GraphQL own-input guard needs a parented issue to mean anything.** A reply whose `parent`
carries no readable `number`, or no `repository`, must not be misread as "no parent": against an
*unparented* issue that misreading cannot be told apart from the correct "no parent" case, so this
check's own tests exercise the guard against a parented issue instead, where a readable-but-wrong
reply and a merely absent parent are distinguishable.

**Two integration-branch cases were weighed and declined for WiseKiosk on 2026-08-02** (more
repository churn than the case was worth, in a product repository) and are not built here either:
multiple sub-issues sharing one integration branch, and nested integration branches. `PROC-007`/
`PROC-008` as implemented take one parent and one level.

## What this does not catch

**A stale verdict.** The check runs once, against the pull request's state at that moment; editing
an issue's labels, milestone, or parent afterward does not re-run it, so a PR that passed stays
green against a ticket whose metadata has since changed to fail it.

**More than 20 closing references.** The Development-field query pages only the first 20 nodes of
`closingIssuesReferences`; a PR closing more issues than that has its later references read
incompletely, and this check fails closed rather than paging further — a recorded gap, not a silent
one.
