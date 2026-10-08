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

# A live key's absence, distinct from a live value of None: exact means exact, so a floor value
# of null matches only an explicit live null, never a merely absent key.
_ABSENT = object()


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


def next_link(headers):
    link = headers.get("Link")
    if not link:
        return None
    match = LINK_NEXT_RE.search(link)
    return match.group(1) if match else None


def _canonicalize(value):
    """Tags a value with its own type, recursively, so a scalar compares type-strict wherever
    it appears -- 1, True and 1.0 are each distinct, even nested in a list or dict -- and a
    dict or list that reaches here (a shape mismatch against the other side) canonicalizes to
    something no scalar's tag can equal. Dict key order never matters; list order never does
    either, so a list's own elements sort by their canonical form before comparing."""
    if isinstance(value, dict):
        return ("dict", tuple(sorted((key, _canonicalize(v)) for key, v in value.items())))
    if isinstance(value, list):
        return ("list", tuple(sorted((_canonicalize(v) for v in value), key=repr)))
    return (type(value).__name__, value)


def values_equal(floor_value, live_value, key=None):
    """Exact equality in canonical, type-tagged form, order-independent for lists. The one
    exception is the required_status_checks parameter's own list, which allows extra live
    entries: each floor entry (canonicalised whole, so an absent integration_id in the floor
    only matches a live entry that also omits it) need only be a member of the live set, not
    the whole list's equal."""
    if key == "required_status_checks" and isinstance(floor_value, list) and isinstance(live_value, list):
        live_canonical = {_canonicalize(entry) for entry in live_value}
        return all(_canonicalize(entry) in live_canonical for entry in floor_value)
    return _canonicalize(floor_value) == _canonicalize(live_value)


def validate_floor_shape(floor):
    """A floor file that is empty or malformed is broken, never a pass and never a shortfall."""
    if not isinstance(floor, dict):
        broken("floor is not a mapping")
    if "rulesets" not in floor:
        broken("floor has no rulesets key")
    rulesets = floor["rulesets"]
    if not isinstance(rulesets, list) or not rulesets:
        broken("floor's rulesets is empty or not a list")
    seen_names = set()
    for entry in rulesets:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            broken("a floor ruleset entry has no name")
        name = entry["name"]
        if name in seen_names:
            broken(f"floor has duplicate ruleset name {name}")
        seen_names.add(name)
        seen_types = set()
        for rule in entry.get("rules") or []:
            if not isinstance(rule, dict) or not isinstance(rule.get("type"), str):
                broken(f"a rule in floor ruleset {name} has no type")
            rule_type = rule["type"]
            if rule_type in seen_types:
                broken(f"floor ruleset {name} has duplicate rule type {rule_type}")
            seen_types.add(rule_type)
            parameters = rule.get("parameters")
            contexts = isinstance(parameters, dict) and parameters.get("required_status_checks")
            if contexts and (not isinstance(contexts, list) or not all(isinstance(c, dict) for c in contexts)):
                broken(f"floor ruleset {name}'s required_status_checks is malformed")


def compare_fields(name, floor_dict, live_dict, path=""):
    """Every key floor_dict lists must equal the live value; a key it does not list is never
    compared. Recurses into a nested mapping both sides agree is a mapping, so a shortfall names
    the full key path (e.g. required_status_checks.strict_required_status_checks_policy); any
    other value, including a list, is compared as one unit by values_equal."""
    ok = True
    for key, floor_value in floor_dict.items():
        full_key = f"{path}.{key}" if path else key
        if isinstance(live_dict, dict) and key in live_dict:
            live_value = live_dict[key]
        else:
            live_value = _ABSENT
        if isinstance(floor_value, dict) and isinstance(live_value, dict):
            if not compare_fields(name, floor_value, live_value, path=full_key):
                ok = False
        elif not values_equal(floor_value, live_value, key=key):
            rendered_live = "missing" if live_value is _ABSENT else live_value
            shortfall(name, f"{full_key}: floor {floor_value}, repository {rendered_live}")
            ok = False
    return ok


def compare_ruleset(name, floor_entry, live):
    """Every field/rule the floor lists for this ruleset must equal the live value; fields and
    rules the floor does not list are never compared. bypass_actors is never compared here --
    it is reported separately, unconditionally. A rule's own parameters compare the same way a
    ruleset's top-level fields do, so a rule with no parameters key has nothing left to compare
    and passes on its type alone, and a shortfall names the full rule_type.parameter path."""
    fields = {k: v for k, v in floor_entry.items() if k not in ("name", "rules", "bypass_actors")}
    ok = compare_fields(name, fields, live)

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
        floor_params = rule.get("parameters") or {}
        live_params = candidates[0].get("parameters") or {}
        if not compare_fields(name, floor_params, live_params, path=rule_type):
            ok = False
    return ok


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    api_url = os.environ.get("GITHUB_API_URL") or "https://api.github.com"
    token = os.environ.get("GITHUB_TOKEN", "")
    pr_head_sha = os.environ.get("PR_HEAD_SHA")

    # .github's own pull requests read the floor at their head commit, so a floor change is
    # tested against itself before it merges; every other case reads main.
    if event_name == "pull_request" and repo.lower() == FLOOR_OWNER_REPO.lower():
        ref = pr_head_sha
    else:
        ref = "main"

    floor_url = f"{api_url}/repos/{FLOOR_OWNER_REPO}/contents/{FLOOR_PATH}?ref={ref}"
    status, _headers, body = api_get(floor_url, token)
    if status != 200:
        broken(f"floor fetch returned {status} for {floor_url}")
    try:
        content = base64.b64decode(json.loads(body)["content"]).decode()
    except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
        broken(f"floor response could not be decoded: {e}")
    try:
        floor = yaml.safe_load(content)
    except yaml.YAMLError as e:
        broken(f"floor is not valid YAML: {e}")

    validate_floor_shape(floor)

    live_entries = []
    url = f"{api_url}/repos/{repo}/rulesets?per_page=100"
    while url:
        status, headers, body = api_get(url, token)
        if status != 200:
            broken(f"rulesets list fetch returned {status} for {url}")
        try:
            page = json.loads(body)
        except json.JSONDecodeError as e:
            broken(f"rulesets list response could not be decoded: {e}")
        live_entries.extend(page)
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
        status, _headers, body = api_get(detail_url, token)
        if status != 200:
            broken(f"ruleset detail fetch returned {status} for {detail_url}")
        try:
            live = json.loads(body)
        except json.JSONDecodeError as e:
            broken(f"ruleset detail response could not be decoded: {e}")

        if not compare_ruleset(name, entry, live):
            any_shortfall = True
        # Bypass is never verifiable with a workflow token, so every floor ruleset found live
        # is reported this way regardless of how it compared.
        print(f"repo-floor: bypass not verified: {name}", file=sys.stderr)

    if any_shortfall:
        sys.exit(1)
    print("repo-floor: repository meets the floor")


if __name__ == "__main__":
    sys.exit(main())
