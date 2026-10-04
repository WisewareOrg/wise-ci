# Contributing to wise-ci

The human contributor entry point: how a change gets merged. **What wise-ci is** is the
[README](README.md); working rules for an AI agent are in [`CLAUDE.md`](CLAUDE.md).

## Before you build anything

**Design-first: nothing is implemented that has not been written down first.** A choice that takes a
trade study gets an [ADR](docs/decisions/README.md). Anything observable a decision does not state —
an interface name, a payload shape, a config key, a failure behaviour, a threshold — becomes a test
before it is built ([`docs/TESTING.md`](docs/TESTING.md)). A new check takes the shape the
[README](README.md) describes.

**Do not build generality against a case that does not exist** — no abstraction without a second
consumer, no comment-enforced invariants, no denylist secret handling, no non-tunable config keys, no
controls that do not function where deployed. A check's first consumer is the repository it migrated
from.

## Tickets, branches, and titles

Open an issue first: the branch name is derived from it. Ticket, branch-naming, linkage and
PR-title rules — including the ticket types (PROC-010) — are stated once in
[WisewareOrg/.github's `PROCESS.md`](https://github.com/WisewareOrg/.github/blob/main/PROCESS.md),
not restated here. The `check-branch` action itself takes no `types` input: PROCESS.md's ticket
types are built into it as-is.

Enforced by the `check-branch` and `pr-title` CI checks.

## Getting a change merged

Size a change by what can be **read in one sitting** — a slice that cannot be reviewed has not been,
whatever its size. Keep the diff to intended files. Verify via CI, not a local run.

**Squash-merge, with the branch's commit messages concatenated into the body** —
`git log --reverse --format='--- %h %s%n%b' <base>..<head>`. The squash makes the PR title the commit
on `main`; without the bodies beneath it, the reasoning recorded per commit is unreachable by
`git log -S` on the line it explains.

## Review checklist

Each question is an obligation on the author that leaves no artifact, so no check decides it — the
reviewer is the mechanism.

**Cite a question by number *and* name** — `question 6, *Generality*`. A bare number resolves silently
to whatever occupies it after a renumber, in documents no sweep reliably reaches. New questions are
appended for the same reason; inserting one is permitted and renumbers everything below.

**Documentation**

1. **Described code.** Where the change touches code or configuration a canonical document describes,
   does it update that document, or say why none is needed? The [index](docs/README.md) says which
   document describes what.
2. **Temporal phrasing.** Does the prose state the timeless fact — no *now*, *no longer*, *as of*?

**Comments**

3. **Mechanism, not reason.** Does each comment state what the code or configuration does, or how?
   Reason, history and judgement are authored in a documentation home and cited from the comment.
4. **Citation, not restatement.** Strip the whole citation out of a comment and read what is left: if
   any assertion still stands on its own, it restates rather than cites.

**Code**

5. **Dependencies.** Does a new dependency do work the standard library cannot reasonably do — and
   what does it bring with it: a native toolchain, a transitive tree, a runtime?
6. **Generality.** Does the change add an interface or extension point with a single implementation
   and no second consumer?
7. **Secrets.** Does an output path the change adds — a log line, an action output, an annotation —
   carry a secret's value rather than its name?
8. **Unjudged input.** What does a check the change touches do with input outside the set it
   recognises? Skipping is the language's default and always wrong for a gate: the check shrinks its
   own population, then reports success over what is left.
9. **Narrowed guards.** Where the change narrows a check so it stops rejecting legal input, is the
   narrowing reachable by the defect the check exists to catch? An exemption is the first place a
   bypass gets spelled, and the reasoning that produces one reads as caution.
10. **Second enforcer.** Does the change add a second place enforcing a rule an ADR allocated to one?
    Two enforcers drift, and the divergence surfaces as one accepting what the other rejects.

**Checks**

11. **Recorded cases.** Does the check's test suite exercise both directions — the defect it must
    catch, and the legal input spelled differently that it must not reject — with each seeded defect
    confirmed to land?
12. **Defects the work surfaced.** Where the work found an existing check **fails to catch what it
    exists to catch, admits what it exists to reject, or reports a result its input cannot support**,
    is that fixed here? Deferring it separates the fix from the only context the defect was visible
    in. Those three clauses are the floor, not a licence to change anything nearby — which is
    question 9, *Narrowed guards*, from the other side.

**Prose**

13. **Counted claims.** Does a sentence the change adds state a count, a roster or an absolute about
    the repository that nothing compares to it? **The test is who falsifies it.** A claim that
    ordinary work elsewhere breaks — migrating a check, merging an ADR — is the failure, because
    nobody doing that work opens the document they just made wrong; a claim about a gate is not, since
    changing one is work on the subject, done by someone reading the sentence. Prefer the rule that
    decides the next case, and where a count is the point, name the commit it was taken at.
14. **Untested premises.** Where the change accommodates a reason an existing document gives — a
    constraint it records, a limitation it accepts — has that reason been tested against the
    repository, or only read? Testing it is usually cheaper than the accommodation, and a stated
    reason that no longer holds is how a workaround gets written for a problem nobody has.
15. **One home.** Is each fact the change states in prose stated in the document that guarantees it?
    The [index](docs/README.md) decides: a *Guarantees* cell is what a document may state, an
    *Excludes* cell is what it must cite instead. **The test is question 4 read one level up** — strip
    the citation out of the sentence, and if what remains still asserts what the cited document
    asserts, it restates rather than cites. Summarizing and citing is permitted; a second independent
    statement is what goes stale in one copy while the other stays right, with nothing comparing them.

**Deletions**

16. **Orphaned names.** Where the change removes a recipe, check, or workflow step, does any
    operator-facing reference to its name survive that no gate reaches — a justfile `[doc()]`, a
    workflow step `name:`, `--help` text? No check resolves a script name in prose against the
    repository; this stays a review habit rather than a check — a check here would have to tell
    operative prose from a rev-pinned historical record, which is judgment.
