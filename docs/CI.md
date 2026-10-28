# Continuous integration

What CI does for this repository, and what it refuses to let through.

**None of this is a requirement.** wise-ci carries no requirements tree — a gate below constrains
this repository's own workflows and hygiene, never a running system. Adding or retiring a gate is an
edit here and a change to the check, not a specification change.

## First-party source scanning

[`../.github/workflows/codeql.yml`](../.github/workflows/codeql.yml)'s `codeql` job runs CodeQL's
default code-scanning suite over the project's own source. The wiring workflow calls it on every
pull request, every push to `main`, and weekly (so a dormant branch is still covered)
([`TESTING.md`](TESTING.md) § In CI).

The CodeQL matrix carries one leg per language of first-party source in the tree; a change that adds
a language adds its leg to the matrix.

No `queries:` input: the action's own default is the code-scanning suite, so widening to a named
suite later is a visible diff rather than a silent one.

**Every check that exists blocks a merge into `main`.** Most do, through one required status
check: the wiring workflow's final job ([`TESTING.md`](TESTING.md)). Every workflow this repository
runs other than `process-gates.yml` is called by the wiring workflow, and that job fails if any of
them failed — checked against the run's own job list, not only its hand-kept `needs:`
([`TESTING.md`](TESTING.md) § In CI) — so adding a check or a CodeQL leg to the wiring workflow
needs no change to branch protection. `check-branch`, `pr-title` and `repo-floor` are the exception:
each is its own required status-check context instead, gated by
[`../.github/workflows/process-gates.yml`](../.github/workflows/process-gates.yml)'s top-level job
of the same name, under the `process-gates` ruleset (`WisewareOrg/.github`'s
`repository-floor.yml`, PROC-011) — adding a fourth such context would need a branch-protection
change.
`gh api repos/WisewareOrg/wise-ci/rules/branches/main` reads the live set. The codeql leg fails only on
an execution error — it is not where a CodeQL finding fails a merge. A finding gates through the
ruleset's own `code_scanning` rule instead, configured for CodeQL at every alert severity. That rule
is ruleset configuration rather than a tracked file, so no check here can assert it.

`process-gates.yml`'s three jobs run `uses: ./check-branch`, `./pr-title` and `./repo-floor` — each
pull request's own copy of the action, not a pinned release — so a pull request that weakens one of
these checks passes its own weakened copy of the gate it is meant to pass. This holds for every
gate this repository defines over its own tree; it is accepted so that a pull request fixing a
broken check can still merge.

This mechanises the security review a solo project has no second reader to perform.

## Workflow supply-chain and privilege audit

The workflows are themselves a supply chain and themselves privileged. Audited from the files in the
`workflow-audit` job ([`../.github/workflows/checks.yml`](../.github/workflows/checks.yml)), each tool
run from a digest-pinned official image: `zizmor` at the `pedantic` persona, with `--strict-collection`,
over the `.github/workflows` input set, for what a workflow may do — action pinning, permission grants,
credential persistence and template injection among its audit set — and `actionlint`, over the same
input set, for whether a workflow is well-formed at all: schema, expression and reference errors, with
`shellcheck` and `pyflakes` over a workflow's own inline `run:` scripts.

- **Every action is pinned to an immutable reference** — a commit SHA, or an image digest where the
  step is a container. A tag is a pointer its owner can move after anyone reviewed it; neither of
  those is. A `uses:` beginning `./` is exempt: a repository-local action or workflow moves with the
  commit that calls it, so there is no upstream to pin.
- **No workflow grants a write permission at the top level, and no grant goes unexplained.**
  `excessive-permissions` fails a top-level write grant, and fails a workflow declaring no
  `permissions:` block at all — what an undeclared block would inherit is a repository setting no
  check here can see. A job needing more elevates in its own block. `permissions: read-all` is
  refused as excessive; every grant other than a bare `contents: read` — read grants included —
  carries an explanatory comment beside it; every checkout sets `persist-credentials: false`; every
  job carries a `name:`, and every workflow a `concurrency:` group.
- **An unreadable workflow fails rather than being skipped.** actionlint parses real YAML and fails on
  what it cannot read. zizmor's own default is to warn on a file it cannot parse and audit whatever
  remains, reporting clean over a narrowed set that dropped the unreadable file — `--strict-collection`
  is what turns that warning into a failure instead, so a workflow neither tool could read fails the
  step rather than being silently absent from zizmor's own audited set.

**What the gate deliberately lets through.** The `workflow-audit` job's zizmor step runs with no
`GITHUB_TOKEN`, so the audits needing the GitHub API — `known-vulnerable-actions` and
`ref-version-mismatch` among them — do not run: the gate runs the offline audit set,
deterministically, so a verdict moves only when a workflow or a pinned image does. A stale or absent
`# vN` version comment beside a pin passes; nothing here enforces its freshness.

**The repository-level default is not decidable here either.** `GITHUB_TOKEN`'s default permission
sits behind an admin-only API. It is read-only; the top-level blocks are what a check can see, and
they are what the rule above constrains.

## Secret scanning

A pull request, every push to the default branch, and the wiring workflow's weekly run are scanned
for committed credentials in the `secret-scan` job. A finding fails the merge on a pull request; on a
push or the weekly run there is no merge to fail, so it fails that run instead.

On a pull request or a push, the scan walks **the commits the event carries** rather than the tree at
its tip — the pull request's own commits, or the commits a push delivered — so a secret added and then
removed within one branch still fails: the value is compromised from the moment it is pushed, and the
commit that removes it changes nothing. On `schedule`, gitleaks-action scans the repository's full
history instead of a commit range — the one path by which this gate does reach behind the branch
point, on a week's delay.

**What a pull request or a push does not reach**, and what may therefore not be read into a green
result between weekly runs: history behind the branch point; a commit reachable only through a merge's
second parent, because the walk follows first parents and skips merges; and the tail of a range longer
than the event's own commit list. The scan is pattern-based besides, so it catches the credential
shapes it holds rules for and nothing reports what it missed. It raises the cost of committing a
credential; it is not an assertion that the repository holds none.

## PR title

The pull request title — the commit that reaches `main` under squash-merge — is a Conventional
Commit, stated once in `WisewareOrg/.github`'s `PROCESS.md` (PROC-009) — what it checks, and what it
does not catch, is [`../pr-title/README.md`](../pr-title/README.md)'s to state. The tool and the
glue it runs through are a trade study
([`decisions/0001-pr-title-commitlint-python-handoff.md`](decisions/0001-pr-title-commitlint-python-handoff.md),
ADR 0001 rev 1). The check runs as a required gate on wise-ci's own pull requests, in
[`../.github/workflows/process-gates.yml`](../.github/workflows/process-gates.yml)'s `pr-title`
job. [`../.github/workflows/pr-title.yml`](../.github/workflows/pr-title.yml)'s own
`expected-failure` job passes the action a `title` input that violates PROC-009 and a non-exempt
`branch` input, and asserts the action's own step outcome is `failure` ([`TESTING.md`](TESTING.md) § The action).

## check-eol

Every file git treats as text is LF-only, over the whole tracked tree — `.gitattributes` decides which
files that is; what it checks, and what it does not catch, is
[`../check-eol/README.md`](../check-eol/README.md)'s to state. The check runs as a required gate on
wise-ci's own tree, in [`../.github/workflows/check-eol.yml`](../.github/workflows/check-eol.yml)'s
`self-check` job, called by the wiring workflow like every other check ([`TESTING.md`](TESTING.md)).

**What the gate deliberately lets through.** [`TESTING.md`](TESTING.md) § The action states the gap
this leaves in check-eol's own action.

## check-docs-index

Every tracked Markdown file outside a top-level dot-directory is claimed by a row in
[`README.md`](README.md)'s index — what it checks, and what it does not catch, is
[`../check-docs-index/README.md`](../check-docs-index/README.md)'s to state. The check runs as a
required gate on wise-ci's own tree, in
[`../.github/workflows/check-docs-index.yml`](../.github/workflows/check-docs-index.yml)'s
`self-check` job, called by the wiring workflow like every other check ([`TESTING.md`](TESTING.md)).

**What the gate deliberately lets through.**
[`../check-docs-index/README.md`](../check-docs-index/README.md) § What this does not catch states
it. [`TESTING.md`](TESTING.md) § The action states the gap this leaves in check-docs-index's own
action.

## check-branch

Branch-shape, ticket-linkage and epic-membership rules, stated once in `WisewareOrg/.github`'s
`PROCESS.md` (PROC-001 through PROC-008, and PROC-010) — what it checks, and what it does not
catch, is [`../check-branch/README.md`](../check-branch/README.md)'s to state. The check runs as a
required gate on wise-ci's own pull requests, in
[`../.github/workflows/process-gates.yml`](../.github/workflows/process-gates.yml)'s `check-branch`
job; `process-gates.yml` triggers on `pull_request` only, so the job never runs outside one, rather
than running and being skipped.

## check-reqs

The shared Doorstop requirements-tree gate a repository runs over its own tree — what it checks, and
what it does not catch, is [`../check-reqs/README.md`](../check-reqs/README.md)'s to state. wise-ci
carries no requirements tree of its own, so the check runs as a required gate over a
minimal tree built on the fly, in
[`../.github/workflows/check-reqs.yml`](../.github/workflows/check-reqs.yml)'s `self-check` job,
called by the wiring workflow like every other check ([`TESTING.md`](TESTING.md)) — that job proves
the action, not any content here. The same workflow's `expected-failure` job seeds a defect onto
that tree and asserts the action's own step outcome is `failure` ([`TESTING.md`](TESTING.md) § The
action).

## repo-floor

Compares a repository's live rulesets against the floor stated once in `WisewareOrg/.github`'s
`repository-floor.yml` (PROC-011) — what it checks, and what it does not catch, is
[`../repo-floor/README.md`](../repo-floor/README.md)'s to state. The check runs as a required gate
on wise-ci's own pull requests, in
[`../.github/workflows/process-gates.yml`](../.github/workflows/process-gates.yml)'s `repo-floor`
job. Its unit suite runs separately, in
[`../.github/workflows/repo-floor.yml`](../.github/workflows/repo-floor.yml)'s `test` job, called
by the wiring workflow like every other check ([`TESTING.md`](TESTING.md)).
