set shell := ["bash", "-uc"]

[doc("List the available recipes.")]
default:
    @just --list

[doc("Run every check's tests with coverage, failing under 100%. Pass a check's folder name to run just that one, scoped to its own coverage. Quiet on success; full pytest/coverage output on failure.")]
test check="":
    @uv run --locked pytest {{ if check == "" { "" } else { "--cov-reset --cov=" + quote(check) + " " + quote(check + "/tests") } }}
