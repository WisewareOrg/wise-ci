set shell := ["bash", "-uc"]

[doc("List the available recipes.")]
default:
    @just --list

[doc("Run every check's tests with coverage, failing under 100%. Pass a check's folder name to run just that one, scoped to its own coverage. Quiet on success; full pytest/coverage output on failure.")]
test check="":
    @uv run --locked pytest {{ if check == "" { "" } else { "--cov-reset --cov=" + quote(check) + " " + quote(check + "/tests") } }}

[doc("CI only: one check's own tests, coverage left unscoped over the job's full checkout, deferring the fail-under verdict to the wiring workflow's merged report (docs/TESTING.md § In CI).")]
test-ci check:
    @COVERAGE_FILE={{ quote(".coverage." + check) }} uv run --locked pytest --cov-fail-under=0 {{ quote(check + "/tests") }}

[doc("CI only: combine every check's uploaded coverage data into one file (docs/TESTING.md § In CI).")]
merge-coverage:
    @uv run --locked coverage combine

[doc("CI only: report the merged coverage, failing under 100% (docs/TESTING.md § In CI).")]
coverage-report:
    @uv run --locked coverage report -m
