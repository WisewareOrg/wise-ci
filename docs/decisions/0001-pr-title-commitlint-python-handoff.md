# 0001 — Check pull-request titles with commitlint, handed the title by a standard-library Python script

**Status:** accepted
**Decided:** 2026-10-14 (wise-ci issue 28 discovery)
**Rev:** 1

## Revisions

- **rev 1** — 2026-10-14 — first written (#28 make the pr-title check callable by every repository).

## Context

PROC-009 (WisewareOrg/.github's `PROCESS.md`) requires every pull request title to be a Conventional
Commit, and that rule must be enforced by a shared action every repository can call, not reimplemented
per repository.

The owner's constraints on how it is enforced:
- one Conventional-Commit ruleset serves both commit messages and pull request titles — the
  motivation behind WiseKiosk's own commitlint setup — because squash-merge makes the pull request
  title the commit that lands on `main`;
- the glue code is Python, standard library only, with no shell logic;
- a maintained off-the-shelf tool is configured rather than a bespoke rule set built from scratch;
- a consumer adds one job block: no config, no install, no checkout, no required inputs.

Release notes generated from `main`'s commits (for example `cz changelog`) read a commit's `scope`
capture verbatim, with no case normalisation
(`commitizen/cz/conventional_commits/conventional_commits.py:41`, commitizen `4.19.2`:
`(?P<scope>[^()\r\n]*)`), and silently skip any commit whose subject the changelog pattern doesn't
match (`commitizen/changelog.py:147-148`, same version: `if not pat.match(commit.message): continue`).
An unlinted `Backend` vs `backend` scope, or `Feat:` instead of `feat:`, corrupts or drops a changelog
entry with nothing raised. The rules checked on a title must therefore be strict and individually
named, not a single catch-all pattern.

## Decision

- commitlint `21.2.3` with `@commitlint/config-conventional@21.2.3`, plus wise-ci's own
  `scope-case: [2, "always", "lower-case"]`, configured by the two moved JSON files
  (`pr-title/.commitlintrc.json`, `pr-title/.commitlintrc-pr-title.json`);
- a stdlib-only `pr-title/pr-title.py` that fetches the pull request's current title and hands it to
  commitlint on stdin;
- pull-request events only; an event that carries no pull request fails closed;
- tests in pytest that run the real commitlint binary, not a mock.

## Alternatives considered

- **commitizen `4.19.2` (Python).**
  `cz check --allowed-prefixes -l 100 --message "<title>"`, with no config file, matches commitlint's
  pr-title config on 16 of 19 titles compared. It disagrees on `feat(Scope): x`, `feat: X Is Start
  Case`, and `feat: x.`: commitizen's schema has no scope-case, subject-case, or subject-full-stop
  rule (`commitizen/cz/conventional_commits/conventional_commits.py:195-218`, v`4.19.2`: the scope
  group `(\(\S+\))?` and the subject group `([^\n\r]+)` carry no case or full-stop constraint).
  Reproducing those three rules needs a `cz_customize` `schema_pattern` regex wise-ci would then own;
  such a regex matched all titles tried, but commitizen reports every failure as the same
  undifferentiated "pattern mismatch", never a named rule id. Its config-file `message_length_limit`
  setting is also silently inert for `cz check`: `commitizen/commands/check.py:54-55` reads
  `arguments.get("message_length_limit", config.settings.get("message_length_limit", 0))`, and
  argparse always inserts the key `message_length_limit` with value `None` when `-l` is omitted, so
  the `dict.get` fallback never triggers and the config file's limit is never consulted — confirmed by
  running `cz check -l 100 --message "<101-char title>"` against the same title with and without `-l`.
- **gitlint.** Unmaintained: last release `v0.19.1`, published 2023-03-10
  (`jorisroovers/gitlint` GitHub releases). Has no subject-case or scope-case rule.
- **conventional-pre-commit.** A fixed regex with no case rules.
- **amannn/action-semantic-pull-request `v6.1.1`.**
  It re-fetches the current title via the REST API rather than trusting the event payload
  (`src/index.js:42`: `const {data: pullRequest} = await client.rest.pulls.get(...)`), but its rules
  are regex-only and it takes no title input, so wise-ci's rules can't be exercised against it outside
  a live pull request. It checks titles only, so the one-ruleset goal with commit messages would need
  PROC-009 reworded around two separate tools.
- **JulienKode/pull-request-name-linter-action `v20.5.0`.**
  It runs commitlint, but reads the title straight from `github.context.payload.pull_request.title`
  (`src/main.ts:26,31`) — the event's snapshot at trigger time, not a re-read — and when that
  snapshot carries no title it returns without failing (`src/main.ts:13-15`): it fails open. It
  takes no title input, and bundles its own commitlint configuration rather than wise-ci's.
- **wagoid/commitlint-github-action.** Checks the pull request's commits, not its title.
- **Shell glue in `action.yml`.** Rejected under the owner's hard rule against shell; its injection
  surface would also move the title out of zizmor's `.github/workflows` input set.
- **`commitlint --env` (title in a file).** commitlint `21.2.3`'s `--env` mode still requires `cwd` to
  resolve a git root; invoked from a directory `git rev-parse --is-inside-work-tree` reports as not a
  repository, it throws `TypeError: Could not find git root` before any rule runs, so a consumer
  would need a checkout to use it. Piping the title to commitlint on stdin needs no git root.
- **Cases run through the action in the workflow, instead of pytest.** Workable, but the owner chose
  plain pytest against the real tool.
- **Re-checking `main`'s head commit on push and weekly.**
  Squash-merge appends ` (#N)` to the landed subject; a title between 94 and 100 characters
  (`header-max-length`'s limit is 100, `@commitlint/config-conventional/lib/index.js:2-37`, v`21.2.3`)
  passes the pull-request check, then fails `header-max-length` on `main` with no remedy once it has
  landed. Under squash-merge plus PROC-012, every commit on `main` has already passed a pull-request
  title check; re-checking it again on push or on a schedule can only turn `main` red for a title the
  pull-request check already passed.

## Consequences

- node is pinned in three places (`pr-title/action.yml`, the `pr-title / test` job, the `ci` job);
  Renovate's node group bumps them together.
- A local `just test pr-title` needs `npm --prefix pr-title ci --ignore-scripts` run first.
- A broken commitlint config fails the same way a bad title does (exit 1). The two are
  distinguishable only by which stream carries the output — a lint failure's report lands on stdout
  with stderr empty, a broken `extends` chain throws a stack trace to stderr with stdout empty — and
  `pr-title.py` does not inspect that.
- Under a fast-forward merge model the pull request title does not land on `main` as the commit
  subject: every pull request merged into `WisewareOrg/mergify-trial` has `merge_commit_sha == head`,
  and Mergify's own `all-commits` squash, where it runs, uses the first original commit's subject,
  never the pull request title. That gap is covered by wise-ci issue 34 and WisewareOrg/.github
  issue 2, not by this decision.
