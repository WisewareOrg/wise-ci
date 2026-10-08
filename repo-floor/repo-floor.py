#!/usr/bin/env python3
"""Enforces PROCESS.md's PROC-011; see repo-floor/README.md.

Dependencies: PyYAML.
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

import yaml

FLOOR_OWNER_REPO = "WisewareOrg/.github"
FLOOR_PATH = "repository-floor.yml"

LINK_NEXT_RE = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


def broken(message):
    print(f"repo-floor: broken: {message}", file=sys.stderr)
    sys.exit(1)


def shortfall(ruleset_name, message):
    print(f"repo-floor: shortfall: {ruleset_name}: {message}", file=sys.stderr)


def api_get(url, token):
    """(status, headers, raw body text) for a single-page GitHub REST call. Callers parse the
    body; this never does, since not every caller wants JSON."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode()
    except urllib.error.URLError as e:
        broken(f"cannot reach {url}: {e.reason}")


def call_api(url, token):
    """api_get, with its network-error exit also enforced here: a caller that replaces api_get
    wholesale (as the test suite's FakeAPI does not, but a network-error test does) must still
    see repo-floor fail closed rather than crash."""
    try:
        return api_get(url, token)
    except urllib.error.URLError as e:
        broken(f"cannot reach {url}: {e.reason}")


def next_link(headers):
    link = headers.get("Link")
    if not link:
        return None
    match = LINK_NEXT_RE.search(link)
    return match.group(1) if match else None


def _canonicalize(value):
    if isinstance(value, dict):
        return tuple(sorted((key, _canonicalize(v)) for key, v in value.items()))
    if isinstance(value, list):
        return _canonical_list(value)
    return value


def _canonical_list(values):
    # GitHub's list ordering carries no meaning (H3), so a list compares as a set: sorted by
    # each element's own repr, since elements may be dicts and not otherwise orderable.
    return tuple(sorted((_canonicalize(v) for v in values), key=repr))


def values_equal(floor_value, live_value):
    """R1/H3: exact equality, type-strict for scalars (so bool != int, int != float), order-
    independent for lists. A floor value of None matches a live None or an absent key (the
    caller passes dict.get()'s None for that case already) because type(None) is type(None)."""
    if isinstance(floor_value, dict):
        return isinstance(live_value, dict) and all(
            values_equal(v, live_value.get(k)) for k, v in floor_value.items()
        )
    if isinstance(floor_value, list):
        return isinstance(live_value, list) and _canonical_list(floor_value) == _canonical_list(live_value)
    return type(floor_value) is type(live_value) and floor_value == live_value


def validate_floor_shape(floor):
    """H4: a floor file that is empty or malformed is broken, never a pass and never a
    shortfall."""
    if not isinstance(floor, dict):
        broken("floor is not a mapping")
    if "rulesets" not in floor:
        broken("floor has no rulesets key")
    rulesets = floor["rulesets"]
    if not isinstance(rulesets, list) or not rulesets:
        broken("floor's rulesets is empty or not a list")
    seen_names = set()
    for entry in rulesets:
        if not isinstance(entry, dict) or "name" not in entry:
            broken("a floor ruleset entry has no name")
        name = entry["name"]
        if name in seen_names:
            broken(f"floor has duplicate ruleset name {name}")
        seen_names.add(name)
        seen_types = set()
        for rule in entry.get("rules") or []:
            if not isinstance(rule, dict) or "type" not in rule:
                broken(f"a rule in floor ruleset {name} has no type")
            rule_type = rule["type"]
            if rule_type in seen_types:
                broken(f"floor ruleset {name} has duplicate rule type {rule_type}")
            seen_types.add(rule_type)


def check_required_status_checks(name, floor_contexts, live_contexts):
    """R5: each floor context must be present live with the same context and the same
    integration_id -- absent in the floor means absent live, present means equal."""
    ok = True
    for floor_context in floor_contexts:
        context = floor_context.get("context")
        floor_has_id = "integration_id" in floor_context
        satisfied = False
        rendered_live = "missing"
        for live_context in live_contexts:
            if live_context.get("context") != context:
                continue
            rendered_live = live_context
            live_has_id = "integration_id" in live_context
            if floor_has_id != live_has_id:
                continue
            if floor_has_id and floor_context["integration_id"] != live_context["integration_id"]:
                continue
            satisfied = True
            break
        if not satisfied:
            shortfall(name, f"required_status_checks: floor {floor_context}, repository {rendered_live}")
            ok = False
    return ok


def compare_ruleset(name, floor_entry, live):
    """R1-R2, R6: every field/rule the floor lists for this ruleset must equal the live value;
    fields and rules the floor does not list are never compared. bypass_actors is never compared
    here -- R7 reports it separately, unconditionally."""
    ok = True
    for key, floor_value in floor_entry.items():
        if key in ("name", "rules", "bypass_actors"):
            continue
        live_value = live.get(key)
        if not values_equal(floor_value, live_value):
            shortfall(name, f"{key}: floor {floor_value}, repository {live_value}")
            ok = False

    live_by_type = {}
    for live_rule in live.get("rules") or []:
        live_by_type.setdefault(live_rule.get("type"), []).append(live_rule)

    for rule in floor_entry.get("rules") or []:
        rule_type = rule["type"]
        candidates = live_by_type.get(rule_type, [])
        if not candidates:
            shortfall(name, f"{rule_type}: missing")
            ok = False
            continue
        if "parameters" not in rule:
            continue  # H3: a floor rule with no parameters key compares type only
        floor_params = rule["parameters"] or {}
        live_params = candidates[0].get("parameters") or {}
        if rule_type == "required_status_checks":
            for key, floor_value in floor_params.items():
                if key == "required_status_checks":
                    if not check_required_status_checks(
                        name, floor_value, live_params.get("required_status_checks") or []
                    ):
                        ok = False
                elif not values_equal(floor_value, live_params.get(key)):
                    shortfall(name, f"{rule_type}: floor {floor_value}, repository {live_params.get(key)}")
                    ok = False
        elif not values_equal(floor_params, live_params):
            shortfall(name, f"{rule_type}: floor {floor_params}, repository {live_params}")
            ok = False
    return ok


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    api_url = os.environ.get("GITHUB_API_URL") or "https://api.github.com"
    token = os.environ.get("GITHUB_TOKEN", "")
    pr_head_sha = os.environ.get("PR_HEAD_SHA")

    # R8/H12: .github's own pull requests read the floor at their head commit, so a floor change
    # is tested against itself before it merges; every other case reads main.
    if event_name == "pull_request" and repo.lower() == FLOOR_OWNER_REPO.lower():
        ref = pr_head_sha
    else:
        ref = "main"

    floor_url = f"{api_url}/repos/{FLOOR_OWNER_REPO}/contents/{FLOOR_PATH}?ref={ref}"
    status, _headers, body = call_api(floor_url, token)
    if status != 200:
        broken(f"floor fetch returned {status} for {floor_url}")
    content = base64.b64decode(json.loads(body)["content"]).decode()
    try:
        floor = yaml.safe_load(content)
    except yaml.YAMLError as e:
        broken(f"floor is not valid YAML: {e}")

    validate_floor_shape(floor)

    live_entries = []
    url = f"{api_url}/repos/{repo}/rulesets?per_page=100"
    while url:
        status, headers, body = call_api(url, token)
        if status != 200:
            broken(f"rulesets list fetch returned {status} for {url}")
        live_entries.extend(json.loads(body))
        url = next_link(headers)

    any_shortfall = False
    for entry in floor["rulesets"]:
        name = entry["name"]
        matches = [live for live in live_entries if live.get("name") == name]
        if not matches:
            shortfall(name, "repository missing")
            any_shortfall = True
            continue
        if len(matches) > 1:
            shortfall(name, "ambiguous")
            any_shortfall = True
            continue

        detail_url = f"{api_url}/repos/{repo}/rulesets/{matches[0]['id']}"
        status, _headers, body = call_api(detail_url, token)
        if status != 200:
            broken(f"ruleset detail fetch returned {status} for {detail_url}")
        live = json.loads(body)

        if not compare_ruleset(name, entry, live):
            any_shortfall = True
        # R7: bypass is never verifiable with a workflow token, so every floor ruleset found
        # live is reported this way regardless of how it compared.
        print(f"repo-floor: bypass not verified: {name}", file=sys.stderr)

    if any_shortfall:
        sys.exit(1)
    print("repo-floor: repository meets the floor")


if __name__ == "__main__":
    sys.exit(main())
