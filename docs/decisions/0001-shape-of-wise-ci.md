# 0001 — wise-ci is one repo of composite actions, consumed by SHA pin

**Status:** accepted
**Decided:** 2026-09-27 (stand-up conversation)
**Rev:** 1

## Revisions

- **rev 1** — 2026-09-27 — first written (stand-up).

## Context

The owner's authored CI checks live scattered across the repositories that use them, each a copy
with its own drift. wise-ci stands the checks up as a repository of their own, homing checks migrated
from WiseKiosk one ticket at a time. Before any check migrates, the shape the repository takes has to
be decided: how a check is packaged, how a consumer pins it, how many release streams it costs, where
its tests live, how bootstrap avoids gating on gates that do not exist yet, and how a maintained tool
like zizmor or commitlint fits beside an authored check.

## Decision

1. **One repo, one composite action per check**, each in its own top-level folder named after the
   check (`check-eol/action.yml`), consumed as `tjwise99/wise-ci/<check>@<sha> # vX.Y.Z`.
2. **One version tag for the whole repo**, semver. A check becoming stricter (rejecting something it
   accepted) is a **major** bump; a new check or a new input is minor; a fix that rejects nothing new
   is patch.
3. **Consumers pin by commit SHA with a version comment**; Renovate's github-actions manager bumps it.
4. **A check's tests live beside it** (`<check>/tests/`) and are its verification record: every
   case a WiseKiosk `scripts/cases/*.md` row states becomes a named test carrying that row's text
   verbatim, every behaviour the check's README claims is pinned by a test, and known gaps are
   pinned as passing tests asserting the gap, each cited by id from the check's own README, where
   owner rulings and gap explanations also move. Test machinery shared across checks lives under
   `tooling/`, not in a check's folder or a top-level folder of its own; a top-level folder holding
   an `action.yml` is a check (point 1). How the tests are tiered, and what each tier guarantees,
   is the test architecture document's, which arrives with the first migrated check.
5. **Migrate-to-enable bootstrap**: wise-ci gates itself with each check as it migrates, via
   `uses: ./<check>`. Consequence recorded: the branch/ticket rules are unenforced here until
   `check-branch` migrates.
6. **Maintained tools are shared as config presets, not wrapped.**

## Alternatives considered

**One repo per check.** Rejected: N release streams, N Renovate pull requests per consumer, for
checks that are meant to be adopted together.

**Reusable workflows as the primary form.** Rejected: they standardise a whole job, and consumers
already have jobs these checks slot into as steps. A reusable workflow may still be added later for a
job whose whole shape repeats.

**Per-check version tags.** Rejected: Renovate and every consumer would track N version streams
instead of one.

**Tag pins instead of SHA pins.** Rejected: a tag is mutable, and zizmor's pedantic persona flags a
mutable action reference.

**Keeping the prose case record** (`scripts/cases/*.md`) as the migrated check's verification
record. Rejected: it is run by hand and nothing gates it — a named test in `<check>/tests/` is what a
CI run actually executes.

**A central `tests/` tree.** Rejected: a check's record belongs beside the check it verifies, so a
check is added, moved or deleted as one folder.

## Consequences

**wise-ci gates itself before any consumer does.** Each migration turns its check on here, via
`uses: ./<check>`, and in the repository it migrated from, on a paired branch.

**The branch/ticket rules run by hand until `check-branch` migrates.** Nothing in wise-ci enforces
branch shape, issue linkage, or PR-base/parent matching mechanically until that check is itself
migrated in.

**No gate script is copied in at stand-up.** Bootstrap is migrate-to-enable: the repository starts
with no checks of its own beyond what a maintained tool provides directly in `checks.yml`
(workflow-audit, secret-scan, pr-title), and each subsequent check arrives already tested and already
gating.
