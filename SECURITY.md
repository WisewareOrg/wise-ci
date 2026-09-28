# Security policy

## Threat model

wise-ci publishes composite GitHub Actions that other repositories execute inside their own CI. A
consumer pins a check to a commit SHA; Renovate's `github-actions` manager, running in the consumer,
proposes each new tag as an update to that pin. A published tag cannot be moved or deleted — the
`tag immutability` ruleset blocks both, for every tag, with no bypass; tag creation is unrestricted.
A minor, patch or digest update automerges in the consumer once that consumer's CI is green, with no
human review; a major update opens a pull request and waits — so the version a release is tagged
with, classified per [ADR 0001 rev 1](docs/decisions/0001-shape-of-wise-ci.md) point 2, decides
whether a human looks before it reaches a consumer.

- **CI holds no custom credential.** The only token any workflow in this repository uses is
  GitHub's own `GITHUB_TOKEN`, scoped per job — read-only for every job in `checks.yml`, and
  `security-events: write` for `codeql.yml`'s job, which needs it to upload results to code scanning.
- **A check's own tests are its verification record**, beside it under `<check>/tests/`
  ([ADR 0001 rev 1](docs/decisions/0001-shape-of-wise-ci.md)) — a check that migrates in without them
  has not migrated.
