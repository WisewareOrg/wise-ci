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
branch names and titles. What covers it: a check's `action.yml` calls only its script, preceded at
most by a pinned dependency-install step from wise-ci's own lock — repo-floor is the one check with
that step, and it takes no caller input — and the script handles the input
([`docs/TESTING.md`](docs/TESTING.md)). zizmor's template-injection audit covers wise-ci's own
workflows, not a check's `action.yml` ([`docs/CI.md`](docs/CI.md)); keeping `action.yml` to that
one script call, plus at most the one unparameterised install step, is what keeps the unaudited
part small.

**wise-ci's own CI is used against it.** What covers it: the only token any workflow uses is GitHub's
own `GITHUB_TOKEN`, scoped per job, with every grant beyond read explained beside it; the one custom
credential, the `GITLEAKS_LICENSE` key gitleaks-action requires of an organization, grants no access
to the repository or its secrets, and the workflows themselves are audited
([`docs/CI.md`](docs/CI.md)).

**A caller's job fetches a package at run time.** repo-floor's `action.yml` is wise-ci's first
action with a runtime dependency: its step runs `setup-uv` and `uv run --frozen` to install PyYAML
from PyPI inside the consumer's own job, rather than running on the stdlib alone. What covers it:
the version is `==`-pinned in `pyproject.toml` and `uv.lock`, Renovate-managed like every other pin
in this repository, and `--frozen` refuses to install anything the lock does not already pin.

**The floor repo-floor checks against is unpinned.** Unlike every other consumer-facing reference
in this repository, repo-floor reads its floor at `main`, not a commit
([`repo-floor/README.md`](repo-floor/README.md)) — a deliberate consequence of what a floor is for,
not an oversight. What this means: `.github`'s own merge rights gate every repository that adopts
repo-floor, since whoever can merge a floor change there changes what every adopting repository's
gate requires, with no pull request on the consumer side to review it first.

**A floor change merges before it is tested against itself.** What covers it: the one exception to
the above ([`repo-floor/README.md`](repo-floor/README.md)) is `.github`'s own pull requests, which
read the floor at that pull request's own head commit instead.
