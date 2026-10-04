#!/usr/bin/env python3
"""The branch name must follow type_number-snake_name, type one of task|bug|design|process
(PROC-001, PROC-010): the number resolves via the GitHub API to an open issue, in this
repository, carrying an open milestone and exactly one type label matching the branch's type
(PROC-003/004/005). The default branch and renovate/* are exempt (PROC-002). When the triggering
pull request exists, its Development field (closingIssuesReferences) must link the branch's
issue, by number and repository (PROC-006); the PR's base and the issue's GraphQL parent must
agree, also by number and repository: no parent for the default branch, a parent anchored at the
base's own number for an integration branch (PROC-007/008).

Runs only inside a pull request: HEAD_REF, PR_NUMBER, DEFAULT_BRANCH, GITHUB_TOKEN and
GITHUB_REPOSITORY are read from the environment at call time, set by action.yml from the
triggering event; there is no argv and no git subprocess, so outside a pull request this fails
closed rather than falling back to a local lookup.

Dependencies: none (stdlib only).
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

TYPES = ("task", "bug", "design", "process")
TYPES_LABEL = "|".join(TYPES)
BRANCH_PATTERN = re.compile(rf"^({TYPES_LABEL})_[1-9][0-9]*-[a-z0-9]+(_[a-z0-9]+)*$")


def fail(message, proc=None):
    tag = f"{proc}: " if proc else ""
    print(f"check-branch: {tag}{message}", file=sys.stderr)
    sys.exit(1)


def matches_shape(name):
    return bool(BRANCH_PATTERN.match(name))


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def api_request(url, token, payload=None):
    """(status, parsed body) for a GitHub REST or GraphQL call; the body parses only
    on 200, which is the only status any caller reads past."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, data=payload)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, None
    except urllib.error.URLError as e:
        fail(f"cannot reach {url}: {e.reason}")


def main():
    branch = os.environ.get("HEAD_REF") or ""
    default_branch = os.environ.get("DEFAULT_BRANCH", "")

    if branch and (branch == default_branch or branch.startswith("renovate/")):
        print(f"Branch '{branch}' is exempt: the default branch and Renovate's own branches "
              "are not work branches.")
        return

    if not matches_shape(branch):
        fail(
            f"branch '{branch}' does not match type_number-snake_name — type one of "
            f"{TYPES_LABEL}, number a GitHub issue number, name lowercase "
            "snake_case (e.g. task_27-process_gates)",
            proc="PROC-001",
        )
    branch_type = branch.partition("_")[0]
    number = int(branch.partition("_")[2].partition("-")[0])

    pr_number = os.environ.get("PR_NUMBER") or ""
    if not pr_number:
        fail("no PR_NUMBER in the environment; check-branch runs only inside a pull request")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    api_base = f"https://api.github.com/repos/{repo}"

    status, issue = api_request(f"{api_base}/issues/{number}", token)
    if status == 404:
        fail(f"issue #{number} does not exist in {repo}", proc="PROC-003")
    if status != 200:
        fail(f"GitHub API returned {status} for {api_base}/issues/{number}", proc="PROC-003")
    if "pull_request" in issue:
        fail(f"#{number} is a pull request, not an issue", proc="PROC-003")
    if issue.get("repository_url", "").lower() != api_base.lower():
        fail(f"issue #{number} is not in {repo} (transferred to another repository?)", proc="PROC-003")
    state = issue.get("state")
    if state != "open":
        fail(f"issue #{number} is {state}, not open", proc="PROC-003")

    label_names = [label["name"] for label in issue.get("labels", [])]
    if branch_type not in label_names:
        labels = ", ".join(label_names)
        fail(
            f"issue #{number} is not labeled '{branch_type}' (labels: {labels or 'none'}) "
            "— the branch type must match the ticket's template label",
            proc="PROC-004",
        )
    type_labels = [name for name in label_names if name in TYPES]
    if len(type_labels) != 1:
        fail(
            f"issue #{number} carries {len(type_labels)} type labels "
            f"({', '.join(type_labels) or 'none'}) — exactly one of {TYPES_LABEL} "
            "names the template it was opened from, and a second makes the branch type "
            "ambiguous",
            proc="PROC-004",
        )

    milestone = issue.get("milestone")
    if milestone is None:
        fail(
            f"issue #{number} has no milestone — the milestone is this repo's phase axis, "
            "and a ticket outside it is absent from the definition of done it belongs to",
            proc="PROC-005",
        )
    if milestone.get("state") != "open":
        fail(f"issue #{number}'s milestone is {milestone.get('state')}, not open", proc="PROC-005")

    print(
        f"Branch '{branch}' links open issue #{number} "
        f"('{issue.get('title')}', labeled '{branch_type}')."
    )

    status, pr = api_request(f"{api_base}/pulls/{pr_number}", token)
    if status != 200:
        fail(f"GitHub API returned {status} for {api_base}/pulls/{pr_number}", proc="PROC-006")
    base_ref = pr["base"]["ref"]

    if not token:
        fail(
            f"PR #{pr_number} requires the recorded-linkage check, which needs GraphQL "
            "auth — a silently skipped gate is a false pass"
        )

    owner, _, name = repo.partition("/")
    query = (
        "query($owner:String!,$repo:String!,$number:Int!,$issue:Int!)"
        "{repository(owner:$owner,name:$repo)"
        "{pullRequest(number:$number){closingIssuesReferences(first:20)"
        "{nodes{number repository{nameWithOwner}}}}"
        " issue(number:$issue){parent{number repository{nameWithOwner}}}}}"
    )
    payload = json.dumps(
        {
            "query": query,
            "variables": {"owner": owner, "repo": name, "number": int(pr_number), "issue": number},
        }
    ).encode()
    status, reply = api_request("https://api.github.com/graphql", token, payload)
    if status != 200:
        fail(f"GitHub GraphQL returned {status}", proc="PROC-006")
    if "errors" in reply:
        fail(
            "GitHub GraphQL errors: "
            + "; ".join(error["message"] for error in reply["errors"]),
            proc="PROC-006",
        )

    repository_data = (reply.get("data") or {}).get("repository") or {}
    pull_request_data = repository_data.get("pullRequest") or {}
    closing = (pull_request_data.get("closingIssuesReferences") or {}).get("nodes") or []
    if not any(
        node.get("number") == number
        and (node.get("repository") or {}).get("nameWithOwner", "").lower() == repo.lower()
        for node in closing
    ):
        fail(
            f"PR #{pr_number}'s Development field does not link issue #{number} in {repo} — "
            f"link it there (a 'Closes #{number}' body keyword writes the same record against "
            "the default branch; other bases need the manual link)",
            proc="PROC-006",
        )
    print(f"PR #{pr_number} records a closing reference to issue #{number}.")

    issue_data = repository_data.get("issue") or {}
    parent = issue_data.get("parent")
    parent_readable = "parent" in issue_data and (
        parent is None
        or (
            is_number(parent.get("number"))
            and isinstance(parent.get("repository"), dict)
            and isinstance(parent["repository"].get("nameWithOwner"), str)
        )
    )
    if not parent_readable:
        fail(
            f"the GraphQL response carries no readable parent for issue #{number} — the "
            "membership check read nothing, and a check that reads nothing must not report "
            "success. A present key with a null value is how 'no parent' arrives; anything "
            "else means the query stopped naming what is read below"
        )
    parent_number = None if parent is None else parent["number"]
    parent_repo = None if parent is None else parent["repository"]["nameWithOwner"]

    if base_ref == default_branch:
        if parent_number is not None:
            fail(
                f"issue #{number} is a sub-issue of #{parent_number}, but PR #{pr_number} "
                "targets the default branch — sub-issue membership means a shared merge "
                "target, not topical grouping; the milestone is what groups",
                proc="PROC-007",
            )
        print(f"Issue #{number} has no parent, and PR #{pr_number} targets the default branch.")
        return

    if not matches_shape(base_ref):
        fail(
            f"PR #{pr_number}'s base '{base_ref}' is neither the default branch nor a "
            "conforming integration branch — an integration branch is a branch, so it links "
            "a ticket of its own",
            proc="PROC-008",
        )
    anchor = int(base_ref.partition("_")[2].partition("-")[0])
    if parent_number is None:
        fail(
            f"PR #{pr_number} targets integration branch '{base_ref}' but issue #{number} "
            f"has no parent — a ticket whose PR targets an integration branch is a sub-issue "
            f"of that branch's anchor #{anchor}",
            proc="PROC-008",
        )
    if parent_number != anchor or (parent_repo or "").lower() != repo.lower():
        fail(
            f"issue #{number} is not a sub-issue of #{anchor} in {repo} — PR #{pr_number} "
            f"targets '{base_ref}', which is anchored at #{anchor} in {repo}; membership "
            "tracks the merge target",
            proc="PROC-008",
        )
    print(f"Issue #{number} is a sub-issue of #{anchor}, which anchors base branch '{base_ref}'.")


if __name__ == "__main__":
    sys.exit(main())
