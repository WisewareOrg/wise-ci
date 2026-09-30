set shell := ["bash", "-uc"]

[doc("List the available recipes.")]
default:
    @just --list

[doc("Run every check's tests with merged coverage, failing under 100%. Pass a check's folder name to run just that one. Quiet on success; full pytest/coverage output on failure.")]
test check="":
    @bash tooling/test.sh {{quote(check)}}
