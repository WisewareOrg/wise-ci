set shell := ["bash", "-uc"]

[doc("List the available recipes.")]
default:
    @just --list

[doc("Run every check's tests with merged coverage, failing under 100%. Pass a check's folder name to run just that one. Quiet on success; full pytest/coverage output on failure.")]
test check="":
    #!/usr/bin/env bash
    set -euo pipefail

    if [ -n "{{check}}" ]; then
        checks=("{{check}}")
    else
        checks=()
        for dir in */; do
            dir="${dir%/}"
            [ -f "$dir/action.yml" ] && checks+=("$dir")
        done
    fi

    log="$(mktemp)"
    trap 'rm -f "$log"' EXIT

    rm -f .coverage .coverage.*
    status=0
    for c in "${checks[@]}"; do
        uv run --locked coverage run -m pytest "$c/tests" >>"$log" 2>&1 || status=1
    done
    if [ "$status" -eq 0 ]; then
        uv run --locked coverage combine >>"$log" 2>&1 || true
        if [ -z "{{check}}" ] && ! bash tooling/coverage-population.sh >>"$log" 2>&1; then
            status=1
        fi
    fi
    if [ "$status" -eq 0 ]; then
        if [ -n "{{check}}" ]; then
            report_args=(--include="{{check}}/*")
        else
            report_args=()
        fi
        if ! uv run --locked coverage report -m "${report_args[@]}" >>"$log" 2>&1; then
            status=1
        fi
    fi

    if [ "$status" -ne 0 ]; then
        cat "$log"
        exit 1
    fi
    echo "test {{ if check == "" { "(every check)" } else { check } }}: passed, 100% coverage."
