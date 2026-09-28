# Security policy

## Threat model

wise-ci publishes composite GitHub Actions that other repositories execute inside their own CI. A
consumer pins a check to a commit SHA and runs exactly that commit's code with whatever permissions
its own workflow grants — there is no mutable tag to trust, and only Renovate's `github-actions`
manager, running in the consumer, moves that pin
([ADR 0001 rev 1](docs/decisions/0001-shape-of-wise-ci.md)).

- **CI holds no custom credential.** The only token any workflow in this repository uses is
  GitHub's own `GITHUB_TOKEN`, scoped per job — read-only for every job in `checks.yml`, and
  `security-events: write` for `codeql.yml`'s job, which needs it to upload results to code scanning.
- **A check's own tests are its verification record**, beside it under `<check>/tests/`
  ([ADR 0001 rev 1](docs/decisions/0001-shape-of-wise-ci.md)) — a check that migrates in without them
  has not migrated.

## Reporting a vulnerability

Report privately via GitHub's **[Private vulnerability reporting](https://github.com/tjwise99/wise-ci/security/advisories/new)**
(Security → Advisories → Report a vulnerability). Please do not open a public issue for a security
report. A fix or triage response is aimed for within a week.
