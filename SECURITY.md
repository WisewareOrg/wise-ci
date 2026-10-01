# Security

## What is at stake

A wise-ci check runs inside a consumer's own CI job, with that job's `GITHUB_TOKEN` and whatever
secrets the job can reach. A bad wise-ci change is therefore a change to every consumer's CI.

## Threats, and what covers each

**A bad release reaches consumers with nobody looking.** A consumer extending the
`WisewareOrg/wise-renovate` preset automerges a minor, patch or digest update once its own CI is green,
with no human review; a major update opens a pull request and waits. The preset exempts `WisewareOrg/`
packages from its release-age delay, so a wise-ci release automerges as soon as it is tagged. What
covers it:

- Consumers pin a commit, not a tag, and the `tag immutability` ruleset blocks moving or deleting any
  tag, with no bypass. A reviewed release cannot be swapped out afterwards.
- The version a release is tagged with, per the [README's versioning rule](README.md#versioning),
  decides whether a consumer's human looks before it lands.
- Every change to wise-ci merges through a pull request that every check gates
  ([`docs/CI.md`](docs/CI.md)).

What is not covered: wise-ci has one maintainer, so that account is the single point of failure —
whoever holds it can merge and tag a minor release that automerges everywhere. Tag creation is
unrestricted.

**A check leaks a consumer's secret.** A check's output — a log line, an annotation — could carry a
value from the consumer's environment. What covers it: review asks of every output a change adds
whether it carries a secret's value ([`CONTRIBUTING.md`](CONTRIBUTING.md), question 7, *Secrets*).

**Attacker-controlled input reaches a shell.** A consumer's pull request supplies its own file names,
branch names and titles. What covers it: a check's `action.yml` only calls its script, and the
script handles the input ([`docs/TESTING.md`](docs/TESTING.md)). zizmor's template-injection audit
covers wise-ci's own workflows, not a check's `action.yml` ([`docs/CI.md`](docs/CI.md)); keeping
`action.yml` to that single call is what keeps the unaudited part small.

**wise-ci's own CI is used against it.** What covers it: CI holds no custom credential — the only
token any workflow uses is GitHub's own `GITHUB_TOKEN`, scoped per job, with every grant beyond read
explained beside it, and the workflows themselves are audited ([`docs/CI.md`](docs/CI.md)).
