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

A check's `action.yml` only calls its script; any logic lives in the script, where the tests reach
it. Nothing in wise-ci proves the action turns a failing script into a red job — a known gap,
accepted, and revisited when the first check takes inputs.

## In CI

Each check has its own workflow file under `.github/workflows/`, which runs the check's tests and
runs the check as a gate on wise-ci itself. That gate is the check's integration test. On a clean
repository it only ever passes, so the failing direction is proven by the tests running the script.

A check's workflow file runs only when the wiring workflow calls it. The wiring workflow runs on every
pull request, never only when certain paths change, and calls every check's workflow. Its final job
merges their coverage into one report, and fails if any check failed or if any line of a check's code
is not run by its tests. A check folder with no tests, or one not wired in, counts as untested and
fails the report. [`CI.md`](CI.md) says how that job blocks a merge. How a check in a language other
than Python joins the one report is decided with the first such check.

## Running tests locally

`just --list` shows the commands. CI runs its commands directly rather than through `just`.
