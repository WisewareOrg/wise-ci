# 0002 — Define the org Python standards once in wise-ci, run them by one command, and type-check with ty

**Status:** accepted
**Decided:** 2026-11-22 (WiseGncDesign issue 19 discovery; wise-ci issue 93)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-22 — first written (wise-ci issue 93 build the org Python standard).

## Context

WiseGncDesign issue 19 asked for a type checker in CI. Discovery found that no org repository ran
one, and that the lint and docstring gates (ruff, interrogate, pydoclint) were copy-pasted inline per
repository with no local entry point, so they drift. The owner's constraints:

- the standards are defined once, here, and run by one command identically in CI and locally;
- ruff is read by the editor from the repository, so its configuration cannot live only here;
- a repository cannot opt out of the standards by editing its own configuration.

## Decision

- **Two checks.** `check-python` runs ruff check, ruff format, interrogate, pydoclint and ty against
  the repository at the working directory, ty pointed at its `.venv`; `check-python-floor` holds the
  repository's `pyproject.toml` to the floor below. Tools are `==`-pinned in wise-ci, and a
  consuming repository takes `check-python` as a `tool.uv.sources` git dependency, which brings the
  same pins into its venv.
- **Configuration.** `[tool.ruff]` stays in each repository, held to the floor. Everything else
  ships inside `check-python`: interrogate and pydoclint options are passed by flag, ty runs on its
  default rules. A repository deletes its own `[tool.interrogate]` and `[tool.pydoclint]`.
- **The floor is an exact allowlist**, so drift is impossible by construction: `[tool.ruff]` may hold
  only `line-length = 120`, `lint.select = ["E", "F", "W", "I", "UP", "B", "SIM", "D", "D417"]`,
  `lint.pydocstyle.convention = "google"` and the repository-specific `src`; `[tool.ty]`,
  `[tool.interrogate]` and `[tool.pydoclint]` must be absent; `requires-python` has a lower bound of
  at least 3.12; a repository tracking Python has a root `pyproject.toml`. A repository tracking no
  Python passes.
- **Scope is every tracked `.py` file, with no exclusions.** interrogate and pydoclint receive
  `git ls-files '*.py'`; ruff and ty honour `.gitignore`.
- **The type checker is ty**, on its default rules. The owner chose it knowingly: it is beta
  (`0.0.x`, "breaking changes, including to diagnostics, between any two versions"), so a Renovate
  bump can change what a repository reports.

## Alternatives considered

The trade study compared pyright, basedpyright, mypy and ty on 2026-11-22 (pyright 1.1.414,
basedpyright 1.40.2, mypy 2.4.1, ty 0.0.107) over WiseGncDesign and WiseDynamics, each at its
default level.

- **basedpyright.** The study's own lean: pyright's engine with the lowest false-positive count (3
  sites in WiseGncDesign, 1 in WiseDynamics), `extends` for a central base file, a mature baseline,
  and node locked through `nodejs-wheel-binaries`. Costs: a community fork, a 282 MB dev dependency,
  and Pylance disabled in the editor. Not chosen: the owner chose ty, knowingly beta. ty is a 39 MB single Rust
  binary with no dependencies, and checks notebooks and runs from the venv in the editor.
- **pyright.** The same detection, but it needs node, which it downloads unpinned unless the
  `[nodejs]` extra is used, it does not check notebooks from the command line, and Pylance bundles a
  lagging copy so editor and CI disagree.
- **mypy.** Caught no finding the others missed, produced the most noise (22 false-positive sites and
  47 configuration-addressable sites in WiseGncDesign), does not check notebooks, and has no
  configuration inheritance.
- **ty's central configuration gap.** ty has no `extends` (astral-sh/ty issue 2137 is open) and
  `--config-file` replaces the project's configuration. A central base file was therefore not
  available, which is why the configuration ships inside `check-python` and why the floor exists.
- **A byte-identical copy of a central ruff configuration in each repository.** Rejected for the
  allowlist: the floor holds the values themselves, and a repository keeps `src`, which is
  repository-specific.
- **ty's recurring false positive.** scipy `Rotation * Rotation` is flagged as
  `missing-union-attribute`; adopting repositories suppress each site with a per-site
  `ty: ignore[missing-union-attribute]` instead of turning the rule off.

## Consequences

- One command, `uv run --locked check-python`, is the same locally and in CI at the same pins.
- Editor settings are untouched, so VS Code's ruff and ty extensions use their bundled versions
  unless pointed at the venv, and their diagnostics may differ from CI's.
- A repository with compiled or generated modules must build them before `check-python`, or ty
  reports them unresolved.
- Adoption is zero findings with no baseline, per repository, as its own ticket; only
  `check-python-floor` becomes a required status-check context.
- ty's diagnostics may move on any version bump.
