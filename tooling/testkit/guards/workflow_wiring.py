"""testkit.guards.workflow_wiring: every check has an action-tests-<check> job with TESTING.md's
§4 step shape, and action-tests aggregates every one (TESTING.md §4 point 6).
"""


def _job_problems(check_name: str, job: dict | None) -> list[str]:
    job_id = f"action-tests-{check_name}"
    if job is None:
        return [f"no {job_id} job"]
    steps = job.get("steps", [])
    problems = []
    invocation = f"./.wise-ci/{check_name}"
    if len([step for step in steps if step.get("uses") == invocation]) < 2:
        problems.append(f"{job_id}: fewer than 2 steps using {invocation}")
    seeded = [step for step in steps if step.get("continue-on-error") and "id" in step]
    if len(seeded) != 1:
        problems.append(f"{job_id}: expected exactly one continue-on-error step carrying an id")
        return problems
    outcome_ref = f"steps.{seeded[0]['id']}.outcome"
    if not any(outcome_ref in str(step.get("if", "")) for step in steps):
        problems.append(f"{job_id}: no later step reads {outcome_ref}")
    return problems


def check(workflow: dict, check_names: set[str]) -> list[str]:
    jobs = workflow.get("jobs", {})
    problems = []
    for check_name in sorted(check_names):
        problems.extend(_job_problems(check_name, jobs.get(f"action-tests-{check_name}")))
    required = {f"action-tests-{name}" for name in check_names}
    aggregate = jobs.get("action-tests")
    if aggregate is None:
        problems.append("no action-tests job")
        return problems
    if not required.issubset(set(aggregate.get("needs", []))):
        problems.append("action-tests: needs does not cover every action-tests-<check> job")
    if aggregate.get("if") != "always()":
        problems.append("action-tests: missing if: always()")
    return problems
