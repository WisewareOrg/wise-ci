# Continuous integration

What CI does for this repository, and what it refuses to let through.

**None of this is a requirement.** wise-ci carries no requirements tree — a gate below constrains
this repository's own workflows and hygiene, never a running system. Adding or retiring a gate is an
edit here and a change to the check, not a specification change.

**No gate here has a local form yet.** `just verify` arrives with the first migrated check
([ADR 0001 rev 1](decisions/0001-shape-of-wise-ci.md)); until then, every gate below is a CI-only
step, run only from its workflow.

## Workflow supply-chain and privilege audit

The workflows are themselves a supply chain and themselves privileged. Both are audited from the
files by two maintained tools, in the `workflow-audit` job
([`../.github/workflows/checks.yml`](../.github/workflows/checks.yml)), each run from a digest-pinned
official image over the `.github/workflows` input set: `zizmor` at the `pedantic` persona for what a
workflow may do — action pinning, permission grants, credential persistence and template injection
among its audit set — and `actionlint` for whether a workflow is well-formed at all: schema,
expression and reference errors, with `shellcheck` and `pyflakes` over `run:` scripts.

- **Every action is pinned to an immutable reference** — a commit SHA, or an image digest where the
  step is a container. A tag is a pointer its owner can move after anyone reviewed it; neither of
  those is. A `uses:` beginning `./` is exempt: a repository-local action moves with the commit that
  calls it, so there is no upstream to pin.
- **No workflow grants a write permission at the top level, and no grant goes unexplained.**
  `excessive-permissions` fails a top-level write grant, and fails a workflow declaring no
  `permissions:` block at all — what an undeclared block would inherit is a repository setting no
  check here can see. A job needing more elevates in its own block. `permissions: read-all` is
  refused as excessive; every grant other than a bare `contents: read` — read grants included —
  carries an explanatory comment beside it; every checkout sets `persist-credentials: false`; every
  job carries a `name:`, and every workflow a `concurrency:` group.
- **An unreadable workflow fails rather than being skipped.** Both tools parse real YAML, so a layout
  that cannot be read is a syntax error, not a skip.

**What the gate deliberately lets through.** The `workflow-audit` job's zizmor step runs with no
`GITHUB_TOKEN`, so the audits needing the GitHub API — `known-vulnerable-actions` and
`ref-version-mismatch` among them — do not run: the gate runs the offline audit set,
deterministically, so a verdict moves only when a workflow or a pinned image does. A stale or absent
`# vN` version comment beside a pin passes; nothing here enforces its freshness.

**The repository-level default is not decidable here either.** `GITHUB_TOKEN`'s default permission
sits behind an admin-only API. It is read-only; the top-level blocks are what a check can see, and
they are what the rule above constrains.

## Secret scanning

A pull request, and every push to the default branch, is scanned for committed credentials, and a
finding fails the merge, in the `secret-scan` job. The scan walks **the commits the event carries**
rather than the tree at its tip — the pull request's own commits, or the commits a push delivered —
so a secret added and then removed within one branch still fails: the value is compromised from the
moment it is pushed, and the commit that removes it changes nothing.

**What that shape does not reach**, and what may therefore not be read into a green result: history
behind the branch point, which this gate does not re-read; a commit reachable only through a merge's
second parent, because the walk follows first parents and skips merges; and the tail of a range longer
than the event's own commit list. The scan is pattern-based besides, so it catches the credential
shapes it holds rules for and nothing reports what it missed. It raises the cost of committing a
credential; it is not an assertion that the repository holds none.

## PR title

The PR title — the commit that reaches `main` under squash-merge — is a Conventional Commit, checked
in the `pr-title` job by commitlint against `.commitlintrc-pr-title.json`, which extends
`.commitlintrc.json` with `defaultIgnores` off — a `fixup!`/`squash!`/merge subject is refused as a
title, since the squash discards it rather than carrying it to `main`. commitlint and
`@commitlint/config-conventional` are pinned in a manifest under `tooling/commitlint/`
(`package.json` and a committed lockfile), installed with `npm ci` rather than as a repository-root
dependency. The PR title is attacker-controlled, so it enters the run step only via env mapping,
never inline into `run:`. The job runs on `pull_request` only — no PR title exists on a push.
