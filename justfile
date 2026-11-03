set shell := ["bash", "-uc"]

[doc("List the available recipes.")]
default:
    @just --list

[doc("Run one check's tests in parallel, coverage scoped to that check and saved to .coverage.<check>, failing under 100%.")]
test check:
    @COVERAGE_FILE={{ quote(".coverage." + check) }} uv run --locked --all-packages pytest -n auto --cov={{ quote(check) }} {{ quote(check + "/tests") }}

[doc("CI only: combine every check's uploaded coverage data into one file (docs/TESTING.md § In CI).")]
merge-coverage:
    @uv run --locked coverage combine

[doc("CI only: report the merged coverage, failing under 100% (docs/TESTING.md § In CI).")]
coverage-report:
    @uv run --locked coverage report -m

[doc("CI only: write the merged coverage as JSON, uncapped, for the population guard to read (docs/TESTING.md § In CI).")]
coverage-json out:
    @uv run --locked coverage json --fail-under=0 -o {{ quote(out) }}
