"""Specifies testkit.guards.workflow_wiring (plan #4 W2, decision 10; strategy §4 point 6): every
check has an action-tests-<check> job with >=2 `uses: ./.wise-ci/<check>` steps, exactly one
continue-on-error step carrying an id, and a later step reading that id's outcome; action-tests
needs every such job and carries if: always().
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


def test_aggregate_missing_a_needed_job_is_a_problem():
    workflow = _valid_workflow()
    workflow["jobs"]["action-tests"]["needs"] = []
    assert check(workflow, {"check-eol"}) != []


def test_aggregate_missing_if_always_is_a_problem():
    workflow = _valid_workflow()
    del workflow["jobs"]["action-tests"]["if"]
    assert check(workflow, {"check-eol"}) != []


def test_valid_wiring_is_clean():
    workflow = _valid_workflow()
    assert check(workflow, {"check-eol"}) == []
