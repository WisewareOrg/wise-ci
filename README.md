# wise-ci

The owner's authored CI checks, packaged as GitHub composite actions for other repositories to use.
Each check lives in its own top-level folder with its `action.yml`; a check with a local form is
also a uv workspace member whose console script the action runs.

## Consuming a check

```yaml
- uses: WisewareOrg/wise-ci/<check>@<sha>
```

That action's own `setup-uv` step puts its pinned `uv` (and its env and problem matchers) on
`PATH` for the rest of the consumer's job, not only for that one step.

Every check with a local form is also a uv dev dependency at the same commit:

```toml
[dependency-groups]
dev = ["<check>"]

[tool.uv.sources]
<check> = { git = "https://github.com/WisewareOrg/wise-ci", subdirectory = "<check>", rev = "<sha>" }
```

run with a recipe invoking `uv run --locked <check>`, with that check's own arguments and
environment — see the check's own README § Run locally. `pr-title` and `repo-floor` have no local
form: neither a pull-request title nor a repository ruleset exists locally, so each stays CI-only.

In CI, the action resolves against wise-ci's own `uv.lock`, so every package a check installs
there is pinned exactly as that lock says, and `uv` itself is pinned by the action's own
`setup-uv` step. Locally, a git dependency's own lock is not read: only a check's `==`-pinned
packages carry a pin into the consumer's own resolution, and anything else resolves fresh there,
with whichever `uv` the consumer's own job or machine runs. `git` and the Python interpreter come
from the runner either way (`pyproject.toml`'s `python-preference = "only-system"`). A consumer
pins only wise-ci's own commit, written twice — the `uses:` sha and the dev dependency's `rev` —
both naming the same commit, moved together: wise-renovate's `wise-ci` group moves both in one
pull request, so it is one version even though it is written twice. The live wise-renovate config
disables its `github-actions` manager for wise-ci and bumps it instead through a custom manager in
that group.

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
