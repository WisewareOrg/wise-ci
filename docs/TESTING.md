# Verification strategy

Governs the wave-one migrations and every later one (not an ADR: the owner ruled on 2026-09-06,
in WiseKiosk, that ADRs are for major architecture and not for test-tier mechanics).

## 0. Findings the design answers

Each was found by reading the scripts, workflows and tickets. None is a hypothesis.

- **F1. `uses: ./<check>` hides the wrong-root defect.** Every wave-one script finds the tree it
  judges from its own path (`Path(__file__).resolve().parent.parent`). With `uses: ./check-eol`,
  the action directory is `$GITHUB_WORKSPACE/check-eol`, so a script at `check-eol/<script>.py`
  lands on `$GITHUB_WORKSPACE` by accident, which is the correct tree. A remote consumer's action
  path is `_actions/tjwise99/wise-ci/<sha>/check-eol`, so the same script judges wise-ci's own
  download there. That download is clean, so the check passes every tree forever. Self-gating
  cannot see this, and neither can an action test that runs from inside the tree it judges.
- **F2. GitHub counts a skipped required status check as passing.** An aggregate job that is skipped
  because a job it `needs` failed therefore reads green.
- **F3. Inherited environment decides verdicts.** CI exports `GITHUB_ACTIONS=true`, which silently
  turns check-eol's "plain stderr" test into the annotated case. A developer's `core.excludesFile`
  hides untracked files from check-untracked and check-eol. A `GIT_DIR` inherited from a git hook
  sends every git call to the wrong repository.
- **F4. check-branch has 24 `fail()` paths, and about half have no case row.** They include: wrong
  type label (`:123`), Development field not linking the issue (`:229`), no token once a PR exists
  (`:188`), a non-conforming base (`:265`), no parent on an integration base (`:272`), a parent that
  is not the anchor (`:279`), detached HEAD with no argument (`:79`), a non-GitHub origin (`:105`),
  an unreachable host (`:62`), non-200 statuses (`:113-115, :170, :177, :213`) and GraphQL errors
  (`:214`).
- **F5. Test modules collide under pytest's default import mode.** Several `<check>/tests/`
  directories will hold modules with the same basename. `check-eol` is also not an importable
  package name.

## 1. Tiers

| Tier | Where it runs | What it guarantees | What it cannot see |
|---|---|---|---|
| **T0 Harness** | `tooling/testkit/tests/`, in `just test` / `tests` | Each piece of test machinery fails when its subject is wrong and passes when it is right: population guard, citation guard, hermetic env, replay transport, coverage completeness guard. Every piece is seeded in both directions. | Anything about a check |
| **T1 Script** | `<check>/tests/`, in `just test` / `tests` | For every case row, every behavioural claim in the README, and every failure path: the check's **real script, run from its real path in the wise-ci tree**, with cwd set to a hermetic temp git repo built by the test, returns the expected exit status **and** the diagnostic that names the reason. check-branch runs here against **recorded real GitHub responses**. | action.yml; the runner; live GitHub |
| **T2 API contract** | check-branch network cases, in `just contract` / `api-contract` (`contract.yml`: push to `main`, weekly; never on PRs) | The same network cases, run **live** against closed-at-rest fixtures in wise-ci, reopened only for the run's window (§3), give the same verdict and diagnostic as T1's recordings. The fixtures hold the state their roles declare. | the `frozen` head-lookup case (§3) |
| **T3 Action** | a per-check `action-tests-<check>` job, plus the `action-tests` aggregate; CI only | **Differential pair:** the action as a consumer runs it, from an archived copy **outside** the tree it judges (F1), on a stock runner. It goes green on a clean fixture tree, then red on the same tree with one seed added, and the seed is confirmed by an independent read. This proves action.yml wiring, the interpreter, exit propagation, and that the action judges the consumer's workspace. | case breadth (T1's job) |
| **Self-gating** | `uses: ./<check>` in wise-ci's own jobs (ADR 0001 point 5) | wise-ci obeys its own checks. This is **product use, not verification.** It adds no fact T3 lacks and is not counted as evidence. | failure direction; F1 |
| **Consumer wiring** | the consuming repository, once, per its own ADR 0010 | The consumer's step is in a required job and turns the build red on a seeded defect. | — |

Each fact is proven at the lowest tier that can see it. Case breadth lives only in T1. T3 carries
exactly one pair per check, because a second pair would re-prove T1. T2 exists only because a
recording cannot tell whether GitHub still answers the way it did.

## 2. Decisions

Each decision gives the choice, the rejected alternative, and a one-line reason.

**D1. Runner: pytest, plus coverage.py, managed by uv.** Dependencies (pytest, coverage, PyYAML,
and `rust-just` for the `just` binary itself) are a `test` dependency-group in the root
`pyproject.toml`, pinned with every transitive dependency and hash in `uv.lock`. The venv is uv's
own default, root `.venv/`, gitignored.
*Rejected: stdlib `unittest`.* Its subtests are not individually addressable, and a case row needs
a test id that a README can cite.
*Rejected: `tooling/python/requirements.txt` plus a hand-maintained venv (this decision's first
form).* uv gives pinned, hashed dependencies with one lockfile and Renovate's built-in support, at
no more mechanism than a `requirements.txt` would have needed (owner, 2026-09-28).

**D2. Interpreter: the runner's stock `python3`. No `setup-python`.**
*Rejected: a pinned `setup-python`.* T1 would then run on a different interpreter from the one a
consumer's composite action gets. If an action later provisions its own Python (a product choice),
T1 follows it.

**D3. Invocation: always the script's real entry point, as a subprocess, from its real path, with
cwd set to the fixture repo.** The script is never copied into the fixture and never imported for
T1.
*Rejected: WiseKiosk's "copy the script into the scratch tree".* That copy is the F1 defect's
disguise, and the stale-copy and md5 traps it needed disappear with it. Running from the real path
also makes every must-fail case discriminate against a wrong-root script.

**D4. Every T1 assertion is a triple.** The exit status is exact (never "non-zero" where the script
defines one). The check's own diagnostic fragment is present: the error line on fail, the success
line on pass. There is no `Traceback`, except in a case whose row *is* a raised error, such as
check-untracked's git-failure row.
*Rejected: exit status alone.* An uncaught exception also exits 1, so a crash would pass every
must-fail row.

**D5. Hermetic by construction, never patched per test.** A single harness builds each test's
environment and repository:
- The environment is built **from an allow-list**, with `PATH` plus explicit values. It is never
  inherited and then scrubbed (F3).
- `HOME` is the test's own temp directory, with `GIT_CONFIG_GLOBAL=/dev/null` and
  `GIT_CONFIG_NOSYSTEM=1`. `GIT_CEILING_DIRECTORIES` is set, author, committer and dates are
  fixed, `LC_ALL=C.UTF-8`, and `git init -b main`.
- Every test gets a fresh `tmp_path` repository. There are no shared repos, no module-scoped
  fixtures that mutate state, and no test depends on another test's order.
- Every seed helper asserts its postcondition **by a mechanism independent of the check**. For
  example, CRLF is confirmed from the file's bytes, not with `git grep`, and untracked-ness is
  confirmed with `git status --porcelain`, not `git ls-files --others`.
- pytest runs with `-p no:cacheprovider`, `--strict-markers`, `--strict-config`,
  `--import-mode=importlib` (F5) and `xfail_strict`.

*Rejected: order randomisation (pytest-randomly).* It adds non-reproducible order to find coupling
that the structure above already rules out.

**D6. Trace: the case table survives as the test table.** Each check's `tests/test_cases.py` holds
its cases as one parametrised table. Each case carries:
- `row`: the case-file Input cell, **verbatim**. A multi-input row becomes several cases that share
  the same text.
- `direction`: `must-fail`, `must-pass` or `gap`.

The test id is `<direction>-<slug>`. At migration, the PR runs a one-off comparison: every row of
the WiseKiosk case file, read at a pinned commit, must appear verbatim in the table. The PR body
shows the output, and the independent reviewer re-runs it. No script is committed, because its
input is deleted in *Switch to the wave-one wise-ci actions*.
*Rejected: a README table mapping rows to tests.* That is a second copy of the tests, and it
drifts.

**D7. Gaps are pinned as passing tests that assert the gap behaviour** (`direction=gap`), and the
check's README cites each one by test id.
*Rejected: `xfail`/`skip`.* They read as "expected to fail" and invert the direction. Closing a gap
already fails a positive gap test, which forces the README ruling to be revisited.

**D8. No skip, no xfail, anywhere.** A root-conftest session hook turns any skipped or xfailed item
into a failed run. A tier that cannot run, for example `just contract` with no token, fails loudly.
*Rejected: skipping when prerequisites are missing.* A skip is a gap nobody sees, and it is the
suppression annotation the owner bans.

**D9. Every behavioural claim in a check's README is pinned by a test.** This covers statements of
rulings, gaps and "what it does not catch", not only case rows. Examples: check-eol's forced-CRLF
blob caught after a fresh clone, and check-untracked's `.git/info/exclude` entry passing.
Unreachable code is removed, never excused.
*Rejected: prose-only README claims.* A claim nothing runs is the unrecorded case the migration
exists to retire.

**D10. Coverage is a gate at 100% branch coverage over every tracked `*.py` outside a top-level
dot-directory.** That population is product scripts, tests and harness, measured in every
subprocess the suite starts. A completeness guard fails the run if the measured set differs from
`git ls-files '*.py'` under the same rule. No pragma exists anywhere; the measured population is
defined by rule, not by an exclusion list, and coverage.py's run-time `omit` of `.venv/` only
mirrors the dot-directory rule. `.claude/` is out by the same top-level-dot-directory rule
`docs/README.md` uses, not by an exclusion list.
*Rejected: WiseKiosk's 90 bar.* On an 80-line check, 90 leaves a whole failure branch unhomed.
100% is the only bar that isn't an arbitrary number, and "no ignore annotations" leaves no other
way to reach it. Including test code catches a misnamed test function, whose body would otherwise
sit dead and green.

**D11. Shared harness: `tooling/testkit/`, with its own `tests/`, a root `conftest.py`, and
`pythonpath = ["tooling"]`.**
*Rejected: a top-level `tests/`.* Under ADR 0001 point 1, a top-level folder reads as a check.

**D12. Consumer help: each check's README has a "Prove the wiring" section that cites its
`action-tests-<check>` seed step by job and step name.** It points at the step and does not
restate it, so it cannot drift.
*Rejected: a `self-test` action input or a shipped canary workflow.* It would prove the action
fails on its own fixture, not that the consumer's real step sits in a required job, which is the
only thing wiring can get wrong.

**D13. Mutation testing is not a gate.**
*Rejected: mutmut or a similar tool.* Survival thresholds would be an arbitrary number. D4's paired
directions, D10 and T1's seeded-script rows already make each guard show it can fail.

## 3. check-branch

**Revised for the owner's clutter constraint (2026-09-27).** The owner's words: *"I dont love the
clutter but a throwaway repo also sucks."* The target is that nothing is open and nothing is red
in wise-ci's default issue and PR views outside a run. Four things changed:

- The standing **open** fixtures (15 issues, 6 draft PRs, some permanently red) are gone.
- Fixtures **rest closed**: 7 issues and 4 PRs that never merge and never run CI. The issues are
  reopened only for the length of a live run.
- T2 left the PR merge gate. It runs on every push to `main` and weekly.
- `just verify` does not include `contract`.

The separate fixtures repository stays rejected (D17). Facts checked on 2026-09-27 before
redesigning:

- **Verified (schema):** GraphQL has `deleteIssue`, `closeIssue`, `reopenIssue`,
  `closePullRequest` and `reopenPullRequest`, and **no** way to delete a pull request.
- **Verified (permissions):** `deleteIssue` needs repository admin. `GITHUB_TOKEN` has no
  `administration` scope, so CI cannot delete an issue without a custom credential.
- **Verified (WiseKiosk PR 228 closed-unmerged, and PR 183, 175, 189):** a **closed, unmerged PR
  keeps its `closingIssuesReferences`**, even after the linked issue closes (PR 228 still lists
  issue 202).
- **Verified (WiseKiosk PR 22):** once a PR's base branch is deleted, REST `pulls/{n}` still
  returns `base.ref` and `base.repo.default_branch`.
- **Read from the script:** check-branch never checks whether the **PR** is open when `PR_NUMBER`
  is given. It also never compares the PR's head with the branch argument. Both matter here: a
  closed PR still carries every PR-phase verdict, and one PR can serve several issues.
- **Read from the script:** every verdict after number resolution needs an **open issue** (`:120`).
- **Unverified, so proven when the fixtures are first built:** that hand-made Development links (on
  non-default bases) survive the PR being closed and its base branch being deleted. The same goes
  for GitHub skipping `pull_request` workflows when the head commit carries `[skip ci]`.

**D14. Merge-gate form: recorded real responses (T1).** No PR-triggered run touches GitHub state.

- **Seam.** A launcher (`python3 <testkit>/replay_run.py <cassette> <script> <args>`) installs the
  transport over `urllib.request.urlopen` and blocks `socket.connect`. It then runs the
  **unmodified** script with `runpy` as `__main__`. argv, exit status and stdio stay real. Only the
  network is replaced, which is not something the check owns. Everything the check owns (URLs,
  query text, parsing and the verdict) runs as shipped.
- **Matching.** Matching is strict and in order. Each request must equal the recorded one on
  method, URL, canonical JSON body and whether an Authorization header is present. Recordings
  never store the header's value. An unrecorded request and an unconsumed recorded exchange each
  exit with a distinct harness code (not 0 or 1), which D4 rejects. A changed query therefore
  cannot silently receive an old answer; it forces a re-record, and a re-record hits live GitHub.
- **Provenance.** Every response body the check parses is recorded from GitHub, never hand-written.
  There are two marked exceptions, and T2 excludes both:
  - `synthetic`: transport faults (non-200 statuses, `URLError`), where the check reads only the
    status.
  - `frozen`: the one case that needs an **open** PR, the `head=` lookup finding a PR with
    `PR_NUMBER` unset. It was recorded live while the fixture PR was open, at build time. The
    recorder never overwrites either kind.
- **Recording.** `just record` runs the network cases live inside a fixture window (D15). It writes
  the per-case files (`check-branch/tests/recordings/<case-id>.json`, sorted keys, LF) **only if
  every case passed live**. A tampered fixture therefore cannot be recorded as truth.
- **Seeded-script rows** keep WiseKiosk's shape. Examples are the `databaseId` selection and the
  regex seeds. Each runs a temp copy of the script or regex with one edit. The test asserts the
  edit landed exactly once, then runs it through the same launcher. The mutated query's response
  is recorded live like any other.

*Rejected: live throwaway issues and PRs per run.* That needs a write token in CI and makes
per-run churn that `GITHUB_TOKEN` cannot delete. Eventual consistency and concurrent runs make it
flaky, and it does not run on forks.
*Rejected: hand-built fake responses.* They mirror the artifact instead of deriving from it.
*Rejected: a local fake HTTP server.* The script hard-codes `https://api.github.com`, so a fake
server needs either a new product input or DNS/TLS tricks.

**D15. Drift is proven by verdict equality, live, inside a fixture window that opens and closes
on every run.** T2 runs the *same* case table live, and every assertion must hold against real
GitHub: same exit status, same diagnostic. That makes a recording and reality equivalent in
everything the check reads. Byte comparison is rejected because responses carry volatile fields
and would flake.

A **window** works like this:
1. `just fixtures-open` reopens the six resting issues that need it (D16).
2. The live cases run, together with the fixture-integrity test. That test reads each fixture
   directly, not through the check, and asserts the state its role declares, so a tampered fixture
   is reported as a fixture fault and not as a check defect. The integrity read is recorded too,
   so T1 checks that each recording matches `fixtures.json`.
3. `just fixtures-close` closes every fixture issue as *not planned* and asserts that all of them
   are closed.

Locally, the recipe guarantees the close with a shell `trap`. In CI, the close is a final step
with `if: always()`. A window has no side effects beyond reopen/close events.

**Where T2 runs:** `contract.yml`, triggered by push to `main`, a weekly schedule and
`workflow_dispatch`. Its one job, `api-contract`, runs a window around `just contract` and the
full-network action pair for check-branch (D18). It has a fixed `concurrency` group with
`cancel-in-progress: false`. Permissions are `contents: read`, `pull-requests: read` and
`issues: write`. `issues: write` is for reopen/close only, using the provided `GITHUB_TOKEN`, so
there is no custom credential. The job never runs on `pull_request`.

**Why not on PRs:**
- A job that mutates shared state must be serialised. GitHub keeps only one pending run per
  concurrency group and cancels the older pending one, so a required PR check would be cancelled
  at random. That is a gate that cannot reliably go green.
- Fork PRs get a read-only token and cannot reopen issues.
- Every PR push would add a window of churn.

**Consequence:** the one thing replay cannot catch, a hand-fabricated recording, is caught by the
push-to-`main` run minutes after merge, not before. **Release rule:** a release tag goes only on
a `main` SHA whose `api-contract` run is green, so a fabricated recording never reaches a
consumer. This is procedural, because tag rulesets cannot require status checks. It goes in the
release section of CONTRIBUTING.md.

**Fewer cases would not reduce churn.** The churn is per window, not per case, and every recorded
exchange that T2 skips becomes unproven. So all network cases run in each window except the
marked `synthetic` and `frozen` ones.

*Rejected: T2 required on every PR.* Its gate could be cancelled at random, it fails on forks, and
it adds a window per push.
*Rejected: weekly-only.* It would give up to a week of exposure to a fabricated recording, with
no per-SHA status to tag against.

**D16. The fixtures rest closed in wise-ci.**
- **Build.** The migration implementer creates them once, with `gh`, and records the commands in
  the PR body. `check-branch/tests/fixtures.json` maps each role to its number and to the
  properties the integrity test asserts.
- **Placement.** The issues are titled `[fixture] check-branch: <role>` and sit in one closed
  milestone, `check-branch fixtures` (all except `no-milestone`).
- **PRs.** Each PR is opened from a head whose single empty commit carries `[skip ci]`, so no
  workflow ever runs on it and nothing is red. Each is linked, then closed unmerged.
- **Branches.** Every fixture branch is then deleted (heads, the integration base and the
  non-conforming base). This is conditional on the first window passing afterwards. If a
  hand-made link or `base.ref` does not survive deletion, the branches stay and that result is
  recorded; branches appear only in the branch list, not in the issue or PR views.
- **Notifications.** The creating account unsubscribes from each fixture issue, so reopen/close
  events notify no one.

**Issues:** 7, all closed at rest.

| Role | Labels, milestone, parent | Reopened in a window | Cases it serves |
|---|---|---|---|
| `base` | `task`, milestone, none | yes | `ok` pass (no `PR_NUMBER`, `head=` lookup returns empty). With M1: unparented→`main` pass. With M2: unlinked fail (`:229`). With B1: bad base fail (`:265`). With I1: **orphan fail** (`:272`, was declined) |
| `member` | `task`, milestone, parent = `anchor` | yes | With I1: **member pass** (was declined), plus the `databaseId` and GraphQL-errors seeds. With M1: parented→`main` fail |
| `stranger` | `task`, milestone, parent = `companion` | yes | With I1: parent ≠ anchor fail (`:279`) |
| `companion` | `design`+`documentation`, milestone | yes | `design_` branch pass. `task_` branch: wrong type fail (`:123`) |
| `no-milestone` | `task`, none | yes | fail |
| `two-types` | `task`+`design`, milestone | yes | fail |
| `anchor` | `task`, milestone | **no** | names the integration base; also serves the **closed-issue** fail row, since it stays closed during windows |

**PRs:** 4, closed and never merged.

| PR | Base | Links | Also serves |
|---|---|---|---|
| M1 | `main` | `Closes #base`, `Closes #member` (body keywords) | the `frozen` `head=` lookup case, recorded before it closed |
| M2 | `main` | nothing | the PR-number row (kind, not existence) |
| I1 | `task_<anchor>-integration_fixture` | `base`, `member`, `stranger`, linked by hand | — |
| B1 | `fixture-nonconforming-base` | `base`, linked by hand | — |

"A number naming nothing" is a number far above the counter. A PR case passes the issue's branch
name as the argument and the fixture PR as `PR_NUMBER`. This is legitimate: the check reads both
independently, and consumers pass `PR_NUMBER` in CI.

**D17. The two integration-branch cases declined on 2026-08-02 are built**, as I1 with `member`
(pass) and `base` (orphan, fail). Their cost is one closed PR and one closed anchor issue, created
once and never added to per run. Without them the non-default-base path (anchor parsing, base
conformance, membership) has no evidence at all. The README keeps the 2026-08-02 ruling as
history, superseded under the 2026-09-27 delegation.
*Rejected: pinning them as gap tests.* A gap test asserts behaviour the check has, and here nothing
would run.
*Rejected: a separate fixtures repository.* The owner rejected it on 2026-09-27.
*Rejected: per-run create and teardown.* Issues could be deleted, but only with an admin
credential stored in CI. Every PR fixture would leave a closed PR behind per run: at least four
per run, hundreds a year, forever. That is the 2026-08-02 churn objection multiplied.
*Rejected: standing open fixtures (rev 1 of this section).* They clutter the default views, and
some are permanently red.

**D18. check-branch's action pair is split by what it can reach without a window.**
- **On every PR:** `action-tests-check-branch` runs read-only. `main` (exempt) goes green. Then
  `task_<anchor>-seed` goes red, because the issue is closed and the check reached the API through
  the consumer's origin and token.
- **Inside the T2 window:** the pair goes past the API. `task_<base>-ok` goes green, then
  `task_<no-milestone>-seed` goes red.

The PR-time pair proves the wiring and exit propagation. Outcome alone cannot prove the *reason*
for the red; T1's diagnostic assertion proves the reason.

**Footprint that remains.**
- **At rest:** 7 closed issues, 4 closed unmerged PRs that never ran CI, 1 closed milestone, no
  branches (unless deletion fails, per D16), and committed recordings plus `fixtures.json`. They use
  11 issue/PR numbers, once. Nothing is open or red in the default views. The fixtures are visible
  under the closed filters and by search (`in:title "[fixture]"`).
- **Per window** (every push to `main`, weekly, and each local `just contract` or `just record`):
  - Six issues show as open for the run's length, about 1–3 minutes.
  - Those six issues each gain a reopen and a close event (12 in all).
  - One Actions run.
  - **No new issue or PR, ever.** Closed PRs do not accumulate.
- **Failure mode:** if a runner is killed mid-window, the close step never runs, and up to six
  fixture issues stay open until the next window or a `just fixtures-close`. Each window ends by
  asserting that all fixtures are closed, so a leak shows red on the next run.
- **Residual unproven live:** the `frozen` found-PR `head=` lookup case. The fields it reads
  (`number`, `base.ref`, `base.repo.default_branch`) are the same `pulls` object fields that T2
  proves through `pulls/{n}`. Only the list endpoint's array wrapper goes without live proof.

## 4. Gates

**`just` recipes.** They have no comments, per house style.

| Recipe | What it runs |
|---|---|
| `test` | `pytest` with **no path or marker arguments** (whole tree), under coverage with subprocess measurement, then combine, the completeness guard, and `fail-under 100`. Offline. |
| `fixtures-open` / `fixtures-close` | reopen the six window issues / close every fixture issue as *not planned* and assert that all are closed (§3 D15) |
| `contract` | `fixtures-open`, then `pytest -m network` with the transport set to live, then `fixtures-close`, guaranteed by a shell `trap`. Fails if `GH_TOKEN`/`GITHUB_TOKEN` is unset (the token needs issue write); it never fetches a token itself. |
| `record` | the same window around the recorder (D14) |
| `verify` | `test` |

`verify` does not include `contract`. Every local verify would otherwise open a fixture window,
racing CI's window and adding churn. T2 runs in CI on every push to `main` and weekly, which
satisfies "every tier must run". The action tier has no local form, and `docs/CI.md` says so.

**CI jobs.** Each job's `name` equals its id. Each job calls the recipe, so the invocation is
spelled in one place.

| Job | What it runs | Required on `main` |
|---|---|---|
| `tests` | `just test` | yes (lands with check-eol) |
| `action-tests-<check>` | one job per check (a fresh workspace each, so no ordering coupling). A matrix cannot vary `uses:`. | through the aggregate |
| `action-tests` | aggregate, `needs:` every `action-tests-*` job, `if: always()`. It fails unless every `needs.*.result` is `success`, which closes F2. | yes |
| `api-contract` (in `contract.yml`) | a window around `just contract` plus the full-network check-branch action pair (§3 D18); push to `main`, weekly, `workflow_dispatch`; fixed concurrency group | **no.** It never runs on PRs. It is the release rule's input: tag only a `main` SHA where it is green (§3 D15). |

**Each `action-tests-<check>` job runs these steps:**
1. Check out wise-ci to a scratch path. Extract `git archive HEAD` into `.wise-ci/`, which uses
   the same export semantics as the tarball a runner downloads for a remote `uses:`. Delete the
   scratch checkout.
2. Run `git init -b main` at the workspace root and add `.wise-ci/` to `.git/info/exclude`.
3. Build the clean fixture, then run `uses: ./.wise-ci/<check>`. It must pass.
4. Seed one defect and confirm the seed by an independent read.
5. Run `uses: ./.wise-ci/<check>` again with an `id` and `continue-on-error: true`.
6. A final step fails unless `steps.<id>.outcome == 'failure'`.

The step names quote the case row they carry.

**What makes an empty or undiscovered population fail.** The first three are root-conftest hooks
that bind whenever pytest runs with no path arguments. They check the collected set **before**
marker deselection.
1. pytest's own exit 5 (nothing collected, or everything deselected) is non-zero. The CI step tests
   the recipe's real exit code, with no pipe.
2. The checks are every top-level directory holding `action.yml` **or `action.yaml`**, since GitHub
   accepts both. Zero checks fails. So does a check whose `tests/` contributes zero items, and a
   check with no `README.md`.
3. Every tracked `test_*.py` or `*_test.py` in the repository contributes at least one collected
   item. This population is deliberately broader than `python_files`, following WiseKiosk's
   `check-dead-test`.
4. The citation guard, in both directions: every test id a check's README cites is collected, and
   every `direction=gap` case is cited by its README.
5. The skip/xfail ban (D8), and the coverage completeness guard (D10). An empty coverage data file
   is an error, not 0 of 0.
6. **The workflow-wiring guard**: a `tooling/testkit` test parses `checks.yml` with PyYAML. Every
   check must have an `action-tests-<check>` job with at least two `uses: ./.wise-ci/<check>` steps,
   exactly one of them `continue-on-error` with an `id`, and a later step that reads that id's
   `outcome`. The aggregate must `need` every such job and carry `if: always()`. `contract.yml`'s
   `api-contract` must open with `fixtures-open`, end with an `if: always()` `fixtures-close` step,
   and carry no `pull_request` trigger.

T0 seeds each of guards 2–6 in both directions against a temp copy of the repo, including a
spelled-differently-but-valid input (an `action.yaml` check, a `*_test.py` file). **Once**, when
each new CI job lands, a pushed seed that turns it red is recorded in that PR's body with the run
URL. After that, the T3 pair re-proves itself on every run.

## 5. ADR 0001 point 4

Point 4's text and the "central `tests/` tree" alternative shipped with the stand-up. ADR 0001
rev 1 point 4 links to this document.

## 6. Test-approach paragraphs for the tickets

Each migration ticket's own body carries this section's paragraph for its check, not this
document.

## 7. Product questions this strategy deferred

Each was decided before the tickets were filed:
- The branch-shape pattern is bundled in check-branch; the branch types are a `types` input.
- check-branch takes a `github-token` input defaulting to the workflow token, and reads the PR
  number, head ref and default branch from the pull-request event. Its README states the
  permissions a consumer grants.
- Actions run the scripts on the runner's stock `python3`, standard library only.
- The default branch is read from the event; `renovate/` stays a constant.
- branch-shape does not migrate as its own action.
