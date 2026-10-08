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

A check's `action.yml` calls only its script, preceded at most by a pinned dependency-install step
from wise-ci's own lock — repo-floor is the one check with that step
([`SECURITY.md`](../SECURITY.md)) — and any logic lives in the script, where the tests reach it.
For check-eol, which takes no inputs, nothing proves the action turns a failing script into a red
job — a known gap, accepted. check-branch, the first check to take inputs, closes that gap for
itself: its workflow's `expected-failure` job runs the action with an input chosen to violate
PROC-001 and asserts the step's own outcome is `failure`. check-reqs's own `expected-failure` job
closes the same gap for itself too, seeding a defect onto the minimal tree its `self-check` job
builds.

Nothing in this repository exercises repo-floor's install step or its action itself: no workflow
here calls `./repo-floor` the way check-branch's own `self-check`/`expected-failure` jobs call
`./check-branch`, a known gap accepted for this ticket and closed by issue 27's self-check.

A GitHub REST response that is valid JSON but the wrong shape for its endpoint -- an object where
a list is expected, or the reverse -- crashes repo-floor rather than reporting it as broken, though
it still exits non-zero; accepted, since GitHub does not send a 200 response in that shape.

## In CI

Each check has its own workflow file under `.github/workflows/`, which runs the check's tests and
runs the check as a gate on wise-ci itself. That gate is the check's integration test. On a clean
repository it only ever passes, so the failing direction is proven by the tests running the script.

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
hand. Each check job runs the justfile's `test-ci` recipe, which leaves its own coverage unscoped
(`pyproject.toml`'s `source = ["."]`, over its own full checkout) and defers its own fail-under
verdict (`--cov-fail-under=0`) — its own coverage is necessarily partial, since it runs only its
own check's tests. `include_namespace_packages = true` is what then makes a check folder's `.py`
file with no executing test show at 0% once the wiring workflow's final job combines every check's
data with the `merge-coverage` recipe, rather than being absent from it.

Each check job also runs `test`'s own one-check branch (`just test <check>`), before `test-ci`, and
the final job also runs its no-argument, full-run branch (`just test`), before downloading any
check's data. Every branch of every recipe therefore runs somewhere in CI, so a typo or a broken
change to any of them, including the one a developer runs locally, fails CI structurally rather than
only a local run. `test <check>` must run before `test-ci` in each check job: `test <check>`'s own
start erases every `.coverage.*` file, which would include `test-ci`'s `.coverage.<check>` were it
run first — `if-no-files-found: error` on the upload step is what catches this class of mistake at
its source if the order is ever wrong.

Which files must appear in the merged report is itself re-derived rather than trusted, in the final
job, between `merge-coverage` and the `coverage-report` recipe that reports it: it lists every
top-level folder with an `action.yml` and that folder's `.py` files outside `tests/`, from its own
checkout, and fails, naming them, if any is missing from the merged coverage data (read with the
`coverage-json` recipe) — independently of the coverage configuration that normally discovers them.
A check job whose own checkout was narrowed, or a coverage configuration that stops discovering a
check's folder, would otherwise drop that check's source out of the report unnoticed rather than
failing it.

## Running tests locally

`just --list` shows every recipe, including the CI-only ones described above (`test-ci`,
`merge-coverage`, `coverage-report`, `coverage-json`). `test` is the one for local use: it runs
`uv run pytest`, configured entirely through `pyproject.toml` (`[tool.pytest.ini_options]`,
`[tool.coverage.run]`, `[tool.coverage.report]`): test discovery, quiet output, coverage source, and
the 100% floor. Passed a check's folder name, it scopes both test collection and coverage to that
check's own `tests/` alone (`--cov-reset --cov=<check> <check>/tests`), matching what the full run's own
`testpaths` glob already collects, so one check's tests are not failed by another, untested check's
source. A local run needs no separate re-derivation step: one `uv run pytest` is a single,
unscoped, unsuppressed coverage session, so an untested check already shows at 0% and fails it
directly. CI's own per-check jobs instead leave coverage unscoped but defer the fail-under verdict,
since their own coverage is only ever partial.
