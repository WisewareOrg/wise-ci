# pr-title

Checks that the pull request title is a Conventional Commit, stated once in
[`WisewareOrg/.github`'s `PROCESS.md`](https://github.com/WisewareOrg/.github/blob/main/PROCESS.md)
(PROC-009). **This restates no requirement** — this check is one of the gates that enforces it. The
tool and the glue it runs through are a trade study, recorded in
[`../docs/decisions/0001-pr-title-commitlint-python-handoff.md`](../docs/decisions/0001-pr-title-commitlint-python-handoff.md)
(ADR 0001 rev 1). `scope-case: lower-case` is wise-ci's own addition on top of
`@commitlint/config-conventional`.

Runs only inside a pull request: outside one, the check fails closed rather than falling back to a
local lookup.

## Inputs

See [`action.yml`](action.yml) for each input's description and default. `title` exists for
`expected-failure` testing: passing it the triggering event's own title snapshot gives up the
current-title re-read (see [The mechanism](#the-mechanism) below), so a consumer has no reason to
set it.

## Consuming pr-title

```yaml
on:
  pull_request:

jobs:
  pr-title:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    steps:
      - uses: WisewareOrg/wise-ci/pr-title@<sha> # vX.Y.Z
```

No checkout: the action carries its own commitlint configs and installs its own dependencies. A
title fix needs the job re-run — `on: pull_request` carries no `edited` type here, so a consumer
wanting that needs its own `edited` trigger.

## The mechanism

The current title is read from the GitHub API, keyed on the triggering event's pull request number
— never the event payload's own title snapshot, which goes stale the moment the title changes.
That title is handed to commitlint on stdin; the configs it lints against are resolved from the
action's own folder, not the consumer's checkout. commitlint's subprocess gets an allowlisted
environment (`pr-title.py`'s `COMMITLINT_ENV_KEYS`), not the job's full one, so `GITHUB_TOKEN` and
anything else the consumer's job carries never reaches it. `setup-node` puts the Node version
pinned in `action.yml` on `PATH` for the rest of the consumer's job, as a side effect of installing
commitlint.

## What this does not catch

**A caller's job not named `pr-title`.** The floor names `pr-title` as a required-status-check
context (`../repo-floor/README.md`); only a top-level job literally named that in the calling
workflow satisfies it, whatever this action's own step is called inside it.

**A broken commitlint config.** It fails the same way a bad title does — exit 1 either way,
distinguishable only by which stream carries the output (`docs/decisions/0001-...md` §
Consequences).

**An install failure, outside a pull request.** `expected-failure`'s step outcome is `failure`
whether the seeded title failed lint or `npm ci` itself broke — the two are indistinguishable there,
so a broken install still reports that job green. On a pull request, `self-check` is what actually
proves the action's own install step, by running it against a title expected to pass; outside one,
that step is skipped, and nothing else exercises it — `test`'s own `npm ci` is a direct workflow
step, not the action's `$GITHUB_ACTION_PATH`-prefixed one.

**A `.py` file shipped inside `node_modules`.** `ci.yml`'s per-check `.py`-file sweep would pick
one up and fail the merged-coverage population guard loudly — not a silent gap, named here because
nothing else in this check's own tests would catch it.

**A landed commit on `main`.** Under a fast-forward merge model, the pull request title this check
lints does not become the landed commit's subject — covered by wise-ci issue 34 (Check that the
commit a pull request lands is a Conventional Commit), not by this check.
