"""Specifies check-branch/check-branch.py: the organization process stated once in
WisewareOrg/.github PROCESS.md (PROC-001-008, PROC-010 -- PROC-009 is commitlint's), ported from
WiseKiosk's scripts/check-branch.py with the behaviour changes and env contract pinned by the
issue-6 plan ("Decisions you are approving") and the owner's 2026-10-03/04 carry comment:
built-in ticket types task/bug/design/process (PROC-010, no `types` input); env read at call time
(HEAD_REF, PR_NUMBER, DEFAULT_BRANCH, GITHUB_TOKEN, GITHUB_REPOSITORY), no argv, no git subprocess;
`api_request`'s own signature and return ((status, parsed-body-or-None)) are unchanged from the
source. `api_request` is replaced here with a URL/payload-dispatching fake for every main()-level
test, since the GitHub API is the one dependency this check cannot use for real
(docs/TESTING.md "Real dependencies where possible"); `api_request`'s own branches are tested
separately below by patching `urllib.request.urlopen` instead.

Every failure test asserts exit 1 and either a `PROC-NNN` substring (the requirement enforced) or,
for a transport/auth/outside-a-pull-request fault, the plain `check-branch: <message>` form with
no PROC tag (plan: "Failure output"). Message text beyond the PROC-NNN substring is asserted only
where the plan pins it as unchanged from the ported source; a NEW or changed path (closed
milestone, a transferred issue, a cross-repository link or parent) is left to its PROC-NNN
substring alone.

Dropped, per the owner's decision ("Local-run fallbacks dropped"): detached-HEAD and non-GitHub-
origin paths, the lookup-PR-by-branch fallback, and the regex-file guards -- none of these exist in
the ported script, so none has a test here.
"""

import importlib.util
import json
import re
import runpy
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-branch.py"
GRAPHQL_URL = "https://api.github.com/graphql"

REPO = "WisewareOrg/wise-ci"
DEFAULT_BRANCH = "main"
TOKEN = "test-token-abc123"  # noqa: S105 -- a fixture value, never a real credential


def _load_module():
    spec = importlib.util.spec_from_file_location("check_branch", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A fresh import, once: the script has no module-level side effects (main() reads env at call
# time, per the plan), so every test below shares this one module object and monkeypatches its
# `api_request` name and the process environment per case.
cb = _load_module()


def _env(monkeypatch, *, head_ref=None, pr_number=None, default_branch=DEFAULT_BRANCH,
          token=TOKEN, repository=REPO):
    for name, value in (
        ("HEAD_REF", head_ref),
        ("PR_NUMBER", pr_number),
        ("DEFAULT_BRANCH", default_branch),
        ("GITHUB_TOKEN", token),
        ("GITHUB_REPOSITORY", repository),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


class FakeAPI:
    """Stands in for check-branch.py's `api_request`. Dispatches on the URL's own shape -- an
    `.../issues/<n>` or `.../pulls/<n>` REST endpoint, or the fixed GraphQL endpoint -- rather
    than a literal URL, so this fake does not also pin how the script builds that URL out of
    GITHUB_REPOSITORY; that construction is code-monkey's to choose; it is not a boundary this
    plan decides. An endpoint this fixture was not given a canned reply for raises, so a main()
    that calls the API in an order or combination a test did not expect fails loudly rather than
    silently returning something plausible.
    """

    def __init__(self):
        self.issue = None
        self.pull = None
        self.graphql = None
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, url, token, payload=None):
        self.calls.append((url, token, payload))
        if url == GRAPHQL_URL:
            if self.graphql is None:
                raise AssertionError(f"unexpected GraphQL call: {url}")
            return self.graphql
        if re.search(r"/issues/\d+$", url):
            if self.issue is None:
                raise AssertionError(f"unexpected issue lookup: {url}")
            return self.issue
        if re.search(r"/pulls/\d+$", url):
            if self.pull is None:
                raise AssertionError(f"unexpected pull lookup: {url}")
            return self.pull
        raise AssertionError(f"unexpected API call: {url}")


def _no_api_call(*_args, **_kwargs):
    raise AssertionError("api_request must not be called")


def _issue(*, number=42, state="open", labels=("task",), milestone="open", repository=REPO):
    return (
        200,
        {
            "number": number,
            "state": state,
            "labels": [{"name": name} for name in labels],
            "milestone": None if milestone is None else {"state": milestone},
            "repository_url": f"https://api.github.com/repos/{repository}",
        },
    )


def _pull(*, number=7, base_ref=DEFAULT_BRANCH):
    # No "repo" key: the plan retires reading base.repo.default_branch (DEFAULT_BRANCH env is the
    # one source now), so a main() that still reaches for it fails with a clear KeyError instead
    # of silently working.
    return (200, {"number": number, "base": {"ref": base_ref}})


def _graphql(*, closing=(), parent=None):
    return (
        200,
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "closingIssuesReferences": {
                            "nodes": [
                                {"number": n, "repository": {"nameWithOwner": r}}
                                for n, r in closing
                            ]
                        }
                    },
                    "issue": {"parent": parent},
                }
            }
        },
    )


def _run(monkeypatch, fake, **env_kwargs):
    monkeypatch.setattr(cb, "api_request", fake)
    _env(monkeypatch, **env_kwargs)


def _expect_fail(monkeypatch, fake, **env_kwargs):
    _run(monkeypatch, fake, **env_kwargs)
    with pytest.raises(SystemExit) as exc_info:
        cb.main()
    return exc_info.value.code


def _expect_pass(monkeypatch, fake, **env_kwargs):
    _run(monkeypatch, fake, **env_kwargs)
    cb.main()  # must return, not raise


# ---------------------------------------------------------------------------------------------
# PROC-001 (branch name shape) / PROC-010 (the ticket-type set the shape is built from)
# ---------------------------------------------------------------------------------------------

NON_CONFORMING_BRANCHES = [
    "nodashes",
    "task-87-name",
    "feature_87-name",
    "task_0-name",
    "task_087-name",
    "task_87-Name",
    "task_87-name_",
    "task_87--name",
    "task_87-",
    "task_-name",
    "module_5-x",  # not one of wise-ci's built-in types -- also a PROC-010 violation
]


@pytest.mark.parametrize("branch", NON_CONFORMING_BRANCHES)
def test_non_conforming_branch_name_fails_before_any_api_call(monkeypatch, capsys, branch):
    """PROC-001 (and, for 'module_5-x', PROC-010: 'module' is not a wise-ci ticket type) --
    every shape violation fails without ever calling the API."""
    code = _expect_fail(monkeypatch, _no_api_call, head_ref=branch, pr_number="7")

    assert code == 1
    captured = capsys.readouterr()
    assert "PROC-001" in captured.err


@pytest.mark.parametrize("branch_type", ["task", "bug", "design", "process"])
def test_each_builtin_ticket_type_is_an_accepted_shape(monkeypatch, branch_type):
    """PROC-001 accepts a conforming name for each of PROC-010's four ticket types. Doubles as
    the PROC-003/004/005/006/007 'fully conforming branch passes' case for every type, and as
    PROC-004's 'one type label removed passes' (exactly one, matching, type label)."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, labels=(branch_type,))
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = _graphql(closing=((42, REPO),), parent=None)

    _expect_pass(monkeypatch, fake, head_ref=f"{branch_type}_42-sample_name", pr_number="7")


# ---------------------------------------------------------------------------------------------
# PROC-002 (exemptions)
# ---------------------------------------------------------------------------------------------


def test_default_branch_is_exempt_even_when_not_named_main(monkeypatch):
    """PROC-002: the exemption follows DEFAULT_BRANCH, not a hardcoded 'main'."""
    _expect_pass(monkeypatch, _no_api_call, head_ref="trunk", default_branch="trunk", pr_number="7")


def test_main_is_not_exempt_when_default_branch_is_not_main(monkeypatch, capsys):
    """PROC-002's exemption is tied to DEFAULT_BRANCH alone: 'main' gets no special treatment
    when the repository's default branch is something else, and falls through to PROC-001."""
    code = _expect_fail(
        monkeypatch, _no_api_call, head_ref="main", default_branch="trunk", pr_number="7"
    )

    assert code == 1
    assert "PROC-001" in capsys.readouterr().err


def test_renovate_prefixed_branch_is_exempt(monkeypatch):
    """PROC-002: Renovate's own naming convention is exempt regardless of shape."""
    _expect_pass(monkeypatch, _no_api_call, head_ref="renovate/x", pr_number="7")


def test_dependabot_prefixed_branch_is_not_exempt(monkeypatch, capsys):
    """PROC-002 names only the default branch and `renovate/*`; a similar-looking prefix from
    another bot is not exempt and falls through to PROC-001."""
    code = _expect_fail(monkeypatch, _no_api_call, head_ref="dependabot/x", pr_number="7")

    assert code == 1
    assert "PROC-001" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------
# PROC-003 (open issue, not a pull request, in the same repository)
# ---------------------------------------------------------------------------------------------


def test_issue_not_found_fails(monkeypatch, capsys):
    """PROC-003: a 404 for the issue lookup."""
    fake = FakeAPI()
    fake.issue = (404, None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-003" in captured
    assert "does not exist" in captured


def test_issue_lookup_other_non_200_fails(monkeypatch, capsys):
    """PROC-003: a non-404, non-200 status for the issue lookup is also a lookup failure."""
    fake = FakeAPI()
    fake.issue = (500, None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-003" in captured
    assert "GitHub API returned 500" in captured


def test_issue_number_names_a_pull_request_fails(monkeypatch, capsys):
    """PROC-003: issues and pull requests share one counter, so the branch's number can resolve
    to a real object of the wrong kind."""
    fake = FakeAPI()
    status, body = _issue(number=42)
    body["pull_request"] = {"url": "https://api.github.com/repos/WisewareOrg/wise-ci/pulls/42"}
    fake.issue = (status, body)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-003" in captured
    assert "is a pull request, not an issue" in captured


def test_closed_issue_fails(monkeypatch, capsys):
    """PROC-003: the issue must be open."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, state="closed")

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-003" in captured
    assert "not open" in captured


def test_issue_transferred_to_another_repository_fails(monkeypatch, capsys):
    """PROC-003 'same repository': a transferred issue's repository_url points elsewhere, which
    GitHub's own redirect would otherwise let resolve silently."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, repository="OtherOrg/other-repo")

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    assert "PROC-003" in capsys.readouterr().err


def test_fully_conforming_branch_passes_case_insensitively_on_repository(monkeypatch):
    """PROC-003's 'same repository' is decided case-insensitively: a repository_url differing
    only in case from GITHUB_REPOSITORY still passes."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, repository="WisewareOrg/Wise-CI")
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = _graphql(closing=((42, REPO),), parent=None)

    _expect_pass(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")


# ---------------------------------------------------------------------------------------------
# PROC-004 (type label)
# ---------------------------------------------------------------------------------------------


def test_missing_branch_type_label_fails(monkeypatch, capsys):
    """PROC-004: the issue carries no label naming the branch's type at all."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, labels=())

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-004" in captured
    assert "is not labeled" in captured


def test_two_type_labels_fails(monkeypatch, capsys):
    """PROC-004: exactly one of the ticket types must be present -- a second makes the type
    ambiguous even though the branch's own type is among them."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, labels=("task", "design"))

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-004" in captured
    assert "carries 2 type labels" in captured


def test_companion_non_type_label_passes(monkeypatch):
    """PROC-004: a label outside the ticket types is permitted alongside the one that matches."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, labels=("task", "needs-triage"))
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = _graphql(closing=((42, REPO),), parent=None)

    _expect_pass(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")


# ---------------------------------------------------------------------------------------------
# PROC-005 (milestone)
# ---------------------------------------------------------------------------------------------


def test_no_milestone_fails(monkeypatch, capsys):
    """PROC-005: the issue carries no milestone at all."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, milestone=None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-005" in captured
    assert "has no milestone" in captured


def test_closed_milestone_fails(monkeypatch, capsys):
    """PROC-005, behaviour change vs WiseKiosk: a closed milestone fails too, not only a missing
    one."""
    fake = FakeAPI()
    fake.issue = _issue(number=42, milestone="closed")

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    assert "PROC-005" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------
# PROC-006 (Development link) -- plus the transport/auth faults encountered on the way to it
# ---------------------------------------------------------------------------------------------


def test_pull_request_lookup_non_200_fails(monkeypatch, capsys):
    """PROC-006: the pull request itself (whose Development field is being checked) must be
    fetchable."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = (500, None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-006" in captured
    assert "GitHub API returned 500" in captured


def test_no_token_fails_without_a_proc_tag(monkeypatch, capsys):
    """The Development-field check needs GraphQL auth; a missing token is an auth fault, not a
    PROC violation, so it carries no PROC-NNN tag (plan: 'Failure output')."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)

    code = _expect_fail(
        monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7", token=""
    )

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-" not in captured
    assert "needs GraphQL auth" in captured


def test_graphql_non_200_fails(monkeypatch, capsys):
    """PROC-006: the combined GraphQL call (Development link + parent) must itself succeed."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = (502, None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-006" in captured
    assert "GitHub GraphQL returned 502" in captured


def test_graphql_errors_field_fails(monkeypatch, capsys):
    """PROC-006: a 200 GraphQL response can still carry an `errors` array."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = (200, {"errors": [{"message": "field not found"}]})

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-006" in captured
    assert "GitHub GraphQL errors" in captured


def test_issue_not_linked_from_a_pr_targeting_the_default_branch_fails(monkeypatch, capsys):
    """PROC-006: the branch's issue is absent from the Development field, with the PR targeting
    the default branch."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = _graphql(closing=(), parent=None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-006" in captured
    assert "does not link" in captured


def test_issue_not_linked_from_a_pr_targeting_an_integration_branch_fails(monkeypatch, capsys):
    """PROC-006 applies the same way regardless of the PR's base -- the link check runs before
    any PROC-007/008 branching, so even an unrelated, non-conforming base does not skip it."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref="some-integration-branch")
    fake.graphql = _graphql(closing=(), parent=None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    assert "PROC-006" in capsys.readouterr().err


def test_development_link_to_the_same_number_in_another_repository_fails(monkeypatch, capsys):
    """PROC-006, behaviour change vs WiseKiosk: a closing reference naming the same issue number
    in a different repository does not satisfy the link -- the same defect class as PROC-008."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = _graphql(closing=((42, "OtherOrg/other-repo"),), parent=None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    assert "PROC-006" in capsys.readouterr().err


def test_development_link_passes_alongside_unrelated_extra_links(monkeypatch):
    """PROC-006: other linked issues are permitted -- only the branch's own issue must appear
    among them."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = _graphql(
        closing=((42, REPO), (999, "OtherOrg/other-repo"), (13, REPO)), parent=None
    )

    _expect_pass(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")


# ---------------------------------------------------------------------------------------------
# PROC-007 (default-branch parent)
# ---------------------------------------------------------------------------------------------


def test_parented_issue_targeting_default_branch_fails(monkeypatch, capsys):
    """PROC-007: a PR targeting the default branch must come from an issue with no parent."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref=DEFAULT_BRANCH)
    fake.graphql = _graphql(
        closing=((42, REPO),), parent={"number": 10, "repository": {"nameWithOwner": REPO}}
    )

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-007" in captured
    assert "targets the default branch" in captured


# ---------------------------------------------------------------------------------------------
# PROC-008 (integration-branch parent)
# ---------------------------------------------------------------------------------------------


def test_integration_base_not_itself_conforming_fails(monkeypatch, capsys):
    """PROC-008: a PR not targeting the default branch must target a branch named per PROC-001."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref="not-a-conforming-branch")
    fake.graphql = _graphql(closing=((42, REPO),), parent=None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-008" in captured
    assert "neither the default branch" in captured


def test_integration_base_with_no_parent_fails(monkeypatch, capsys):
    """PROC-008: targeting a conforming integration branch requires the issue to be a sub-issue
    of that branch's anchor issue -- an unparented issue is not one."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref="task_10-anchor")
    fake.graphql = _graphql(closing=((42, REPO),), parent=None)

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-008" in captured
    assert "has no parent" in captured


def test_integration_base_with_wrong_parent_number_fails(monkeypatch, capsys):
    """PROC-008: the parent's number must match the integration branch's anchor number."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref="task_10-anchor")
    fake.graphql = _graphql(
        closing=((42, REPO),), parent={"number": 99, "repository": {"nameWithOwner": REPO}}
    )

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    captured = capsys.readouterr().err
    assert "PROC-008" in captured
    assert "anchored at" in captured


def test_integration_base_with_parent_in_another_repository_fails(monkeypatch, capsys):
    """PROC-008, behaviour change vs WiseKiosk: a correctly numbered parent in a different
    repository does not satisfy the sub-issue requirement -- cross-repository parents are not
    supported."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref="task_10-anchor")
    fake.graphql = _graphql(
        closing=((42, REPO),),
        parent={"number": 10, "repository": {"nameWithOwner": "OtherOrg/other-repo"}},
    )

    code = _expect_fail(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")

    assert code == 1
    assert "PROC-008" in capsys.readouterr().err


def test_integration_base_with_correct_parent_passes(monkeypatch):
    """PROC-008: the parent matches the integration branch's anchor by both number and
    repository."""
    fake = FakeAPI()
    fake.issue = _issue(number=42)
    fake.pull = _pull(base_ref="task_10-anchor")
    fake.graphql = _graphql(
        closing=((42, REPO),), parent={"number": 10, "repository": {"nameWithOwner": REPO}}
    )

    _expect_pass(monkeypatch, fake, head_ref="task_42-sample_name", pr_number="7")


# ---------------------------------------------------------------------------------------------
# Outside a pull request, and the check-order consequence of that check running after PROC-001
# ---------------------------------------------------------------------------------------------


def test_missing_pr_number_outside_a_pull_request_fails_without_a_proc_tag(monkeypatch, capsys):
    """Decisions: 'Outside a pull request (no PR_NUMBER/HEAD_REF): the script fails with a
    message -- fail closed', and transport/auth/outside-PR faults carry no PROC-NNN tag. A
    conforming, non-exempt branch with no PR number demonstrates this directly."""
    code = _expect_fail(monkeypatch, _no_api_call, head_ref="task_42-sample_name", pr_number=None)

    assert code == 1
    captured = capsys.readouterr().err
    assert "check-branch:" in captured
    assert "PROC-" not in captured


def test_missing_head_ref_fails_on_shape_not_as_an_outside_pr_fault(monkeypatch, capsys):
    """Check order is exemptions -> shape -> outside-PR -> API checks (plan: 'Check order'): an
    absent HEAD_REF resolves to an empty branch name, which PROC-001's shape check rejects before
    the dedicated outside-PR check is ever reached -- so this fails as PROC-001, not as the
    generic outside-PR fault above."""
    code = _expect_fail(monkeypatch, _no_api_call, head_ref=None, pr_number=None)

    assert code == 1
    assert "PROC-001" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------
# api_request itself: its own branches, patching urllib.request.urlopen (not api_request)
# ---------------------------------------------------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_api_request_200_parses_the_json_body(monkeypatch):
    def fake_urlopen(_request):
        return _FakeHTTPResponse(200, {"ok": True})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    status, body = cb.api_request("https://api.github.com/repos/x/y", "")

    assert (status, body) == (200, {"ok": True})


def test_api_request_http_error_returns_its_status_code(monkeypatch):
    def fake_urlopen(request):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    status, body = cb.api_request("https://api.github.com/repos/x/y", "")

    assert (status, body) == (404, None)


def test_api_request_url_error_fails_cannot_reach(monkeypatch, capsys):
    def fake_urlopen(_request):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit) as exc_info:
        cb.api_request("https://api.github.com/repos/x/y", "")

    assert exc_info.value.code == 1
    captured = capsys.readouterr().err
    assert "cannot reach" in captured
    assert "PROC-" not in captured


def test_api_request_sends_authorization_only_with_a_token(monkeypatch):
    requests_seen = []

    def fake_urlopen(request):
        requests_seen.append(request)
        return _FakeHTTPResponse(200, {})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    cb.api_request("https://api.github.com/repos/x/y", "")
    cb.api_request("https://api.github.com/repos/x/y", TOKEN)

    assert "Authorization" not in requests_seen[0].headers
    assert requests_seen[1].headers.get("Authorization") == f"Bearer {TOKEN}"


def test_api_request_never_prints_the_token(monkeypatch, capsys):
    def fake_urlopen(_request):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit):
        cb.api_request("https://api.github.com/repos/x/y", TOKEN)

    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err


# ---------------------------------------------------------------------------------------------
# __main__ guard -- coverage for `sys.exit(main())`, without a pragma
# ---------------------------------------------------------------------------------------------


def test_dunder_main_guard_runs_main_and_exits(monkeypatch):
    """Runs the script the way the action does (`python3 check-branch.py`), to cover the
    `if __name__ == "__main__":` line itself. Uses a scenario that fails before any API call
    (missing PR_NUMBER) so it needs no `api_request` patch of its own module-fresh run."""
    _env(monkeypatch, head_ref="task_42-sample_name", pr_number=None)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert exc_info.value.code == 1
