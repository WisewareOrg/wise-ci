# wise-ci

The owner's authored CI checks, packaged as GitHub composite actions and consumed by other
repositories by commit SHA. Each check lives in its own top-level folder
(`<check>/action.yml`), one semver tag for the whole repository, bumped by Renovate in the consuming
repo — the same consumption model as [`tjwise99/wise-renovate`](https://github.com/tjwise99/wise-renovate).
Checks migrate in one ticket at a time, each migration bringing the tests that are the check's
verification record and turning the check on here as well as in the repository it migrated from.
Maintained tools — zizmor, actionlint, lychee, Trivy, CodeQL, commitlint — are consumed as config
presets, never re-wrapped in a new action. The shape, and the rejected alternatives, are
[ADR 0001 rev 1](docs/decisions/0001-shape-of-wise-ci.md).

## Consuming a check

```yaml
- uses: tjwise99/wise-ci/<check>@<sha> # vX.Y.Z
```

Renovate's `github-actions` manager bumps the pin and its version comment together. No check has
migrated yet, so there is nothing to pin.

## Documentation

- [`docs/README.md`](docs/README.md) — the documentation index: which document guarantees which
  kind of fact.
- [`docs/CI.md`](docs/CI.md) — every check this repository runs on itself: what it asserts and what
  it lets through.
- [`docs/decisions/`](docs/decisions/README.md) — the decisions that carried a rejected alternative.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — tickets, branches, titles, and getting a change merged.
- [`SECURITY.md`](SECURITY.md) — the threat model and how to report a vulnerability.
- [`CLAUDE.md`](CLAUDE.md) — working rules for an AI agent in this repo.
