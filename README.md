# wise-ci

The owner's authored CI checks, packaged as GitHub composite actions for other repositories to use.
Each check lives in its own top-level folder with its `action.yml`.

## Consuming a check

```yaml
- uses: tjwise99/wise-ci/<check>@<sha> # vX.Y.Z
```

A consumer pins a commit, with the version as a comment, and Renovate's `github-actions` manager
bumps both together.

## Versioning

One version number covers the whole repository. The version tracks whether a consumer has to edit
their workflow, not how strict a check is:

- **Major** — a check or an input is removed or renamed, or an input becomes required.
- **Minor** — a new check, a new optional input, or a check catching more than it did.
- **Patch** — a fix.

A stricter check is safe at minor: the consumer's Renovate pull request runs their CI, which goes
red before the new version reaches their `main`.

## Maintained tools

A tool someone else maintains — zizmor, commitlint, and the like — is decided tool by tool. As much as
possible is centralised here, though many such tools carry configuration specific to each project.

## Documentation

- [`docs/README.md`](docs/README.md) — the documentation index: which document guarantees which
  kind of fact.
- [`docs/CI.md`](docs/CI.md) — every check this repository runs on itself: what it asserts and what
  it lets through.
- [`docs/TESTING.md`](docs/TESTING.md) — how a check is tested.
- [`docs/decisions/`](docs/decisions/README.md) — the decisions that took a trade study.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — tickets, branches, titles, and getting a change merged.
- [`SECURITY.md`](SECURITY.md) — the threat model.
- [`CLAUDE.md`](CLAUDE.md) — working rules for an AI agent in this repo.
