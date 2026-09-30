# Documentation index

Every fact about wise-ci has exactly one canonical home: a document that guarantees it. Every other
document may cite or summarize that fact, but never restates it as independent content. This table is
that referenceable definition: a citation resolves, and every tracked document is claimed by a row
here unless it sits under a top-level dot-directory, which holds machinery rather than documents. The
scope is facts *about wise-ci*; how a particular check works internally is a fact about that check,
not about the repository, and belongs in the check's own README once one exists.

An agent's tooling is a fact about whoever holds the tools, so **no document here names one**: not a
skill, vendored or global, and not the command that invokes it. A document that reaches for one is
describing its own author rather than the repository, and states the obligation the tool carries
instead.

| Document | Guarantees | Excludes |
|---|---|---|
| [`../README.md`](../README.md) | What wise-ci is, how a repository consumes a check, how releases are versioned, and the entry point to every other document | A trade study (an ADR); what a check asserts and why (`CI.md`) |
| [`CI.md`](CI.md) | **Every check on this repository**: what CI provides, what blocks a merge, what each gate is allowed to let through, and the reasoning for each stance | A trade study (an ADR); a check a machine cannot decide (`../CONTRIBUTING.md`); how a check is tested (`TESTING.md`) |
| [`TESTING.md`](TESTING.md) | How a check is tested: where its tests live, what they use, and what CI runs of them | What blocks a merge (`CI.md`); a check's own behaviour (`<check>/README.md`) |
| [`decisions/`](decisions/README.md) | A decision that took a trade study, carried as a versioned document: merged text is revisable, each correction is a rev, and every citation of one pins the rev it read | What a check asserts, and why (`CI.md`) |
| `<check>/README.md` | That check's own behaviour, the rulings made about it, and its gap explanations | A trade study (an ADR); what a check asserts on the repository's behalf (`CI.md`) |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | How a change gets made and merged, and **the design-first rule**: nothing is implemented that has not been written down first | What a check asserts, and why (`CI.md`); what wise-ci is (`../README.md`); working rules specific to an AI agent (`../CLAUDE.md`) |
| [`../SECURITY.md`](../SECURITY.md) | The threat model | Repository truth (`../README.md`); what a check asserts (`CI.md`) |
| [`../CLAUDE.md`](../CLAUDE.md) | Working rules layered on top for an AI agent — review independence, and halt-and-ask where a decision is silent | Any fact about wise-ci (every document above) |
