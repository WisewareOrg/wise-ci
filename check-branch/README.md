# check-branch

Enforces the branch-shape, ticket-linkage and epic-membership rules stated once in
[`WisewareOrg/.github`'s `PROCESS.md`](https://github.com/WisewareOrg/.github/blob/main/PROCESS.md)
(PROC-001 through PROC-008, and PROC-010; PROC-009, the PR-title convention, is commitlint's, not
this check's). **This restates no requirement** — wise-ci carries no requirements tree
([`../docs/CI.md`](../docs/CI.md)); `PROCESS.md` is the one place these rules are decided, and this
check is one of the gates that enforces them.

The branch name is `type_number-snake_name` — `type` one of `task`, `bug`, `design`, `process`
(PROC-010), `number` a GitHub issue number, `snake_name` lowercase snake_case (PROC-001). The
default branch and `renovate/*` are exempt (PROC-002). `number` must resolve to an issue, in the
same repository, that is open, carries exactly one of the four type labels matching the branch's
own type, and an open milestone (PROC-003/004/005). Once the triggering pull request exists, its
Development field (`closingIssuesReferences`) must link that issue, by number and repository
(PROC-006); the PR's base and the issue's GraphQL parent must then agree — no parent for the
default branch, a parent anchored at the base branch's own number, in the same repository, for an
integration branch (PROC-007/008).

Runs only inside a pull request: outside one, the check fails closed rather than falling back to a
local lookup.

## Inputs

| Input | Default | |
|---|---|---|
| `github-token` | `${{ github.token }}` | Token for the GitHub REST and GraphQL calls this check makes. |
| `branch` | `${{ github.event.pull_request.head.ref }}` | The branch name to check. Overridable for a workflow that needs to check a branch other than the triggering PR's own head — this repository's own `expected-failure` CI job does. |

## Consuming

```yaml
- uses: WisewareOrg/wise-ci/check-branch@<sha> # vX.Y.Z
```

`contents: read` is the only permission this needs on a public repository — every REST and GraphQL
call it makes reads data a public repository exposes to an unauthenticated or read-scoped token. A
private consumer additionally needs `issues: read` and `pull-requests: read`.

## History

**The branch types are built in, not a `types` input.** `PROCESS.md`'s PROC-010 fixes the ticket-
type set at `task`, `bug`, `design`, `process`; a consumer with a different set is not this check's
case to generalise for. This also retires `branch-shape.regex`'s file-based pattern, and with it the
generality that file carried: each of its non-blank lines was an independent alternative pattern, not
only a type-set list — nothing in `PROCESS.md` asks for that generality, and no input reintroduces
even the narrower form (a type-set substituted into one fixed pattern) that an earlier design for
this migration considered. That file's design needed two guards, not one: a name matching *some*
line proved only that *a* pattern matched, not that the type read out of it was the file's one
authoritative type group — a file whose lines disagreed on the type set could satisfy the first
guard while the second caught it. A single fixed pattern with one alternation has only the one
question this script asks.

**A type-label count must count only type labels.** An issue carrying a second, non-type label (this
repository's own tickets often do) is not ambiguous — only a second label drawn from the four-type
set is. The count PROC-004 enforces is over labels in that set, not over an issue's label count at
large.

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

## Rejected alternatives

Carried forward from WiseKiosk's ADR 0006 and ADR 0013, where the alternative is about an
obligation this check now owns — tagged by the PROC ID it bears on; an alternative about PROC-009
(the PR title) or about where in WiseKiosk's own process convention lived is WiseKiosk's own
history, not this check's.

- **GitHub-native rulesets** (PROC-001, PROC-010): branch-name and commit-message pattern
  restrictions are Enterprise-only — a control that would be inert where this repository runs.
- **Decoupling branch types from issue templates** (PROC-001, PROC-010): rejected because it loses
  the property that a branch's type names the template its ticket was opened from.
- **A shape-only check that never resolves the issue** (PROC-003): a typo'd number would pass, and
  the link the check exists to prove would go unchecked.
- **Regex over the PR body for a closing keyword** (PROC-006): prose can claim a link the platform
  never recorded — observed live on a stacked PR carrying the keyword with an empty
  `closingIssuesReferences`. The check reads GitHub's recorded state, never the text.
  **CI writing the linkage itself, via a write-scoped token** (PROC-006): gates verify; they do not
  mutate.
- **Detecting a bad ticket at issue-creation time, or auditing the whole backlog on a schedule or
  from every pull request** (PROC-004, PROC-005): GitHub has no required check for issue creation,
  so every candidate is after-the-fact detection; gating it at the branch's own pull request reaches
  exactly the change whose ticket is wrong, never an unrelated one.
- **Deferring the sub-issue gate for want of a second consumer** (PROC-007, PROC-008): rejected —
  the historical record already held an instance the gate would have caught (a PR merged into an
  integration branch while its ticket was never that branch's sub-issue).

## What this does not catch

**A stale verdict.** The check runs once, against the pull request's state at that moment; editing
an issue's labels, milestone, or parent afterward does not re-run it, so a PR that passed stays
green against a ticket that would now fail it.

**More than 20 closing references.** The Development-field query pages only the first 20 nodes of
`closingIssuesReferences`; a PR closing more issues than that has its later references read
incompletely, and this check fails closed rather than paging further — a recorded gap, not a silent
one.
