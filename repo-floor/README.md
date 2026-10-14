# repo-floor

Compares a repository's live rulesets against the floor stated once in
[`WisewareOrg/.github`'s `repository-floor.yml`](https://github.com/WisewareOrg/.github/blob/main/repository-floor.yml)
(PROCESS.md PROC-011). **This restates no requirement** — this check is one of the gates that
enforces it.

Every ruleset the floor names must exist live under exactly that name, case-sensitive, among every
ruleset the repository's rulesets endpoint lists, organization rulesets included; two live rulesets
sharing a floor name are a shortfall ("ambiguous"). Every field and rule the floor lists for it must
match the live value exactly:

- **Type-strict at every depth** — `0`, `false` and `0.0` are three different values.
- **A list compares as a set** — order never matters, but an extra or missing element is a
  shortfall. The one exception is `required_status_checks`' own list of contexts: each floor entry
  must be present live, and extra live entries pass. An entry matches whole, on `context` and
  `integration_id` together, so a floor entry without `integration_id` matches only a live entry
  that also has none.
- **A floor `null` matches only an explicit live `null`**, never an absent key.
- **A key the floor lists that is absent live is a shortfall**, so a key misspelled in the floor
  fails rather than going unchecked.

A ruleset, rule, field or key the floor does not mention is never compared, so a repository may
carry any of those beyond the floor.

A value the floor lists is matched exactly, not as a minimum: a repository requiring one approving
review where the floor states `0`, or adding a `release/*` pattern to a floor ruleset's `include`,
falls short. A stricter setting belongs in a ruleset of the repository's own, which the floor never
compares.

A required bypass actor list is never verifiable with a workflow token, so every floor-named ruleset
found live is reported "bypass not verified" regardless of who can actually bypass it. A read
failure — a fetch error, a 404, a rate limit, a floor file that is empty or malformed — fails the
run as "broken", never as a shortfall and never as a pass.

The floor's location (`WisewareOrg/.github`, `repository-floor.yml`, `main`) is fixed in the
script, not an input: `WisewareOrg/.github`'s own pull requests are the one exception, reading the
floor at that pull request's head commit instead, so a floor change is tested against itself before
it merges.

## Inputs

See [`action.yml`](action.yml) for the one input's description and default.

`contents: read` is the only permission this needs. See [`../README.md`](../README.md) §
Consuming a check for how to reference this action. The action runs a Python script with
[uv](https://docs.astral.sh/uv/): the caller's runner needs a system Python meeting
`pyproject.toml`'s `requires-python`; its absence fails the step itself, not as a shortfall.

## What this does not catch

**Bypass.** `bypass_actors` and `current_user_can_bypass` are both absent from the ruleset-detail
response under a workflow token, so repo-floor can never confirm who can bypass a floor-named
ruleset — only that the ruleset itself exists and matches. "Bypass not verified" is reported for
every floor ruleset found live, on every run, pass or fail.

**A repository that never calls this action.** repo-floor only checks a repository that adopts it
as a gate; a repository short of the floor that never runs this check stays unnoticed.

**A required-status-check context satisfied by the wrong job.** This floor pins `integration_id`
alongside each context, so a context is not satisfied by just any check run sharing its name —
only by one from the same GitHub App. `integration_id` identifies GitHub Actions in general,
though, not wise-ci specifically: any GitHub Actions job in the calling repository named
`check-branch`, `pr-title` or `repo-floor` satisfies the matching context, whether or not it is the
job the floor intends.

**A caller's job not named for its context.** A required-status-check context such as
`check-branch` or `repo-floor` is satisfied by a top-level job literally named that in the calling
repository's workflow — not by whatever a composite-action step inside it is called. A caller whose
job wraps this action under a different top-level name produces a different context than the floor
names, and the live repository then falls short of the floor repo-floor is itself checking.

**A GitHub response of the wrong shape.** A REST response that is valid JSON but the wrong shape
for its endpoint — an object where a list is expected, or the reverse — crashes repo-floor rather
than reporting it "broken", though the run still exits non-zero. Accepted: GitHub does not send a
200 response in that shape.
