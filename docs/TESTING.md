# Testing

How a check in wise-ci is tested.

## Every case is a test

Every case is a test, and this is test-driven development: the test is written first, then the code
that makes it pass. Defensive code is allowed only where a test can reach it; code no test can reach
does not belong. A case file carried over from the repository a check migrated from is a seed of
cases, not an exhaustive list, and a test owes it no naming or traceability.

## Where tests live

A check's tests sit directly in `<check>/tests/`.

A check about a language's code may be written in that language; a general-purpose check defaults to
Python. A Python check is tested with pytest, and test dependencies are pinned with uv, in
`pyproject.toml` and `uv.lock`. How a check in another language is tested is decided with the first
such check.

## Real dependencies where possible

A test uses the real thing where possible, and mocks only a dependency it cannot use for real, such
as the GitHub API. A test creates its defective input on the fly, in a temporary folder, so nothing
defective is committed for wise-ci's own checks to trip on. A test gives the same result on any
machine and in CI: the machine's own git configuration is shut out, and each case sets any CI-only
environment variable the check reads, such as `GITHUB_ACTIONS`.

## The action

A check's `action.yml` calls only its script, preceded at most by dependency-install steps that take
no caller input: installing only what wise-ci's own lock pins, setting up the check's runtime at an
exact version, or both; any logic lives in the script, where the tests reach it. For check-eol,
which takes no inputs, nothing proves the action turns a failing script into a red job — a known
gap, accepted; check-docs-index and check-adrs, which take none either, carry the same one.
check-branch, which takes inputs, runs its workflow's `expected-failure` job with an
input chosen to violate PROC-001 and asserts the step's own outcome is `failure` — but shares
repo-floor's recorded condition below: a broken uv setup would read the same way, so
`process-gates.yml`'s `check-branch` job passing, which a broken setup could not do, is what
proves the setup instead. check-reqs's own `expected-failure` job seeds a defect onto the minimal
tree its `self-check` job builds, and shares the same condition: a broken uv setup also fails it,
so that same `self-check` job's own passing run is what proves the setup.

repo-floor's own `expected-failure` job passes the action an invalid `github-token`, so the floor
fetch itself breaks, and asserts the step's own outcome is `failure` — proving only that the
action turns a failing run into a red job, no more: a broken install would read the same way,
the same indistinguishability [`../pr-title/README.md`](../pr-title/README.md) § What this does
not catch states for pr-title's own `expected-failure` job. The install step itself is proven by
`process-gates.yml`'s `repo-floor` job passing, which a broken install could not do. The
shortfall-specific comparison stays covered by its unit suite alone: repo-floor's floor location
and target repository are fixed by design, not a consumer-overridable input, so no workflow here
can arrange a live shortfall to seed.

## In CI

Each check has its own workflow file under `.github/workflows/`, which runs the check's tests
and, for check-eol, check-docs-index, check-adrs and check-reqs, also runs the check as a gate on
wise-ci itself, in that same workflow file. That gate is the check's integration test. On a clean
repository it only ever passes, so the failing direction is proven by the tests running the
script. `check-branch`, `pr-title` and `repo-floor` are gated instead from `process-gates.yml`, a
separate workflow with its own top-level job of each check's name, which the wiring workflow does
not call.

A check's workflow file runs only when the wiring workflow calls it. The wiring workflow runs on every
pull request, every push to `main`, and weekly, never only when certain paths change, and calls every
check's workflow. Its final job merges their coverage into one report, and fails if any check failed
or if any line of a check's code is not run by its tests. A check folder with no tests, or one not
wired in, counts as untested and fails the report. [`CI.md`](CI.md) says how that job blocks a merge.
How a check in a language other than Python joins the one report is decided with the first such check.

The final job's own `needs:` list is hand-kept, so it is not trusted alone: the job also asks the
GitHub API for every job in its own run and fails if any of them, other than itself, is not complete
with a successful conclusion — a job added to the wiring workflow without being added to `needs:`
would otherwise run unwatched rather than blocking the merge.

CI runs every pytest and coverage command through a `just` recipe, never the tool directly, so a
broken recipe fails the CI step that calls it the same way it would fail a developer running it by
hand. Each check job runs `just test <check>` once, in parallel under pytest-xdist, scoped to that
check's own tests and source, and fails below 100% on its own check's coverage. Its coverage data
is written to `.coverage.<check>` and uploaded for the final job to combine.

Which files must appear in the merged report is itself re-derived rather than trusted, in the final
job, between the `merge-coverage` and `coverage-report` recipes: it lists every git-tracked `.py`
file outside `tests/` at any depth, mirroring `pyproject.toml`'s own `omit` pattern, and fails,
naming them, if any is missing from the merged coverage data (read with the `coverage-json`
recipe) — independently of the coverage configuration that normally discovers them.

## Running tests locally

`just --list` shows every recipe, including the CI-only ones described above (`merge-coverage`,
`coverage-report`, `coverage-json`). `test` is the only entry point, the same locally and in CI: it
runs `uv run pytest -n auto`, configured through `pyproject.toml` (`[tool.pytest.ini_options]`,
`[tool.coverage.run]`, `[tool.coverage.report]`): quiet output and the 100% floor. It requires a
check's folder name, and collects only `<check>/tests` and measures coverage over `<check>` alone
(`--cov=<check> <check>/tests`), so one check's tests are not failed by another, untested check's
source.

`pr-title/tests` run the real commitlint: `npm --prefix pr-title ci --ignore-scripts` installs it
and must run before `just test pr-title`.
