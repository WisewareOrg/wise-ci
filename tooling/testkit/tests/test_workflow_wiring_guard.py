"""Specifies testkit.guards.workflow_wiring. TESTING.md §4 point 6: every check has an
action-tests-<check> job with >=2 `uses: ./.wise-ci/<check>` steps, exactly one continue-on-error
step carrying an id, and a later step reading that id's outcome; action-tests needs every such job
and carries if: always().
"""

from testkit.guards.workflow_wiring import check


def _valid_workflow(check_name: str = "check-eol") -> dict:
    job_id = f"action-tests-{check_name}"
    return {
        "jobs": {
            job_id: {
                "name": job_id,
                "steps": [
                    {"uses": f"./.wise-ci/{check_name}"},
                    {
                        "id": "seed",
                        "continue-on-error": True,
                        "uses": f"./.wise-ci/{check_name}",
                    },
                    {"if": "steps.seed.outcome == 'failure'", "run": "exit 0"},
                ],
            },
            "action-tests": {
                "name": "action-tests",
                "needs": [job_id],
                "if": "always()",
                "steps": [{"run": "true"}],
            },
        }
    }


def test_missing_action_tests_job_for_a_check_is_a_problem():
    workflow = {"jobs": {}}
    assert check(workflow, {"check-eol"}) != []


def test_job_missing_a_second_uses_step_is_a_problem():
    workflow = _valid_workflow()
    workflow["jobs"]["action-tests-check-eol"]["steps"] = [
        {"uses": "./.wise-ci/check-eol"}
    ]
    assert check(workflow, {"check-eol"}) != []


def test_job_with_no_continue_on_error_id_step_is_a_problem():
    workflow = _valid_workflow()
    for step in workflow["jobs"]["action-tests-check-eol"]["steps"]:
        step.pop("continue-on-error", None)
        step.pop("id", None)
    assert check(workflow, {"check-eol"}) != []


def test_continue_on_error_step_with_no_outcome_read_is_a_problem():
    workflow = _valid_workflow()
    steps = workflow["jobs"]["action-tests-check-eol"]["steps"]
    workflow["jobs"]["action-tests-check-eol"]["steps"] = steps[:2]
    assert check(workflow, {"check-eol"}) != []


def test_aggregate_missing_a_needed_job_is_a_problem():
    workflow = _valid_workflow()
    workflow["jobs"]["action-tests"]["needs"] = []
    assert check(workflow, {"check-eol"}) != []


def test_aggregate_missing_if_always_is_a_problem():
    workflow = _valid_workflow()
    del workflow["jobs"]["action-tests"]["if"]
    assert check(workflow, {"check-eol"}) != []


def test_two_unrelated_uses_steps_is_a_problem():
    # review-tests: the count must be steps whose uses: is specifically ./.wise-ci/<check>, not
    # any step carrying a uses: key (e.g. an unrelated actions/checkout). Isolated from the other
    # requirements: this job still has a continue-on-error+id step and an outcome-reading step, so
    # zero real check invocations is the only defect present.
    workflow = _valid_workflow()
    workflow["jobs"]["action-tests-check-eol"]["steps"] = [
        {"uses": "actions/checkout@v4"},
        {"uses": "actions/setup-node@v4"},
        {"id": "seed", "continue-on-error": True, "run": "false"},
        {"if": "steps.seed.outcome == 'failure'", "run": "exit 0"},
    ]
    assert check(workflow, {"check-eol"}) != []


def test_uses_prefix_collision_with_a_different_check_is_a_problem():
    # review-tests: startswith(f"./.wise-ci/{check_name}") matches "./.wise-ci/check-eol-other"
    # too -- a different check that merely shares the name as a prefix. Isolated from the other
    # requirements: continue-on-error+id and outcome-read are both present, referencing one of the
    # colliding steps, so zero *exact* check-eol invocations is the only defect seeded.
    workflow = _valid_workflow()
    workflow["jobs"]["action-tests-check-eol"]["steps"] = [
        {"uses": "./.wise-ci/check-eol-other"},
        {"id": "seed", "continue-on-error": True, "uses": "./.wise-ci/check-eol-other"},
        {"if": "steps.seed.outcome == 'failure'", "run": "exit 0"},
    ]
    assert check(workflow, {"check-eol"}) != []


def test_valid_wiring_is_clean():
    workflow = _valid_workflow()
    assert check(workflow, {"check-eol"}) == []
