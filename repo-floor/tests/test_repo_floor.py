"""Tests repo-floor.py: compares a repository's live GitHub rulesets against the floor stated
once in WisewareOrg/.github's repository-floor.yml (PROCESS.md PROC-011).

The pure comparison helpers (`values_equal`, `compare_fields`, `compare_ruleset`,
`validate_floor_shape`) are exercised directly with plain dicts/lists -- no YAML, no API double,
no `main()`. `main()`-level tests, via a `FakeAPI` double for `api_get`, cover what only `main()`
does: the read path (including malformed responses), ruleset-name matching, bypass reporting,
collecting every shortfall rather than stopping at the first, ref selection, and output/exit
codes. `api_get` itself is tested separately at the bottom, patching `urllib.request.urlopen`.
"""

import base64
import importlib.util
import json
import re
import runpy
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "repo-floor.py"

API_URL = "https://api.github.com"
REPO = "WisewareOrg/wise-ci"
TOKEN = "test-token-xyz789"  # noqa: S105 -- a fixture value, never a real credential

FLOOR_OWNER_REPO = "WisewareOrg/.github"
FLOOR_PATH = "repository-floor.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("repo_floor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rf = _load_module()


def _env(monkeypatch, *, repository=REPO, event_name="push", api_url=API_URL, token=TOKEN,
          pr_head_sha=None):
    for name, value in (
        ("GITHUB_REPOSITORY", repository),
        ("GITHUB_EVENT_NAME", event_name),
        ("GITHUB_API_URL", api_url),
        ("GITHUB_TOKEN", token),
        ("PR_HEAD_SHA", pr_head_sha),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def _headers(link=None):
    """The same object type urllib hands `api_get` for a real response: case-insensitively keyed,
    so a test double built on this does not pin which case repo-floor.py queries "Link" by."""
    message = Message()
    if link:
        message["Link"] = link
    return message


def _ruleset(name="process-gates", target="branch", enforcement="active", conditions=None,
             bypass_actors=None, rules=None):
    """One floor ruleset entry, as a plain dict -- the builder `_floor_yaml` dumps to YAML."""
    return {
        "name": name,
        "target": target,
        "enforcement": enforcement,
        "conditions": conditions if conditions is not None else {
            "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
        },
        "bypass_actors": bypass_actors or [],
        "rules": rules or [],
    }


def _floor_yaml(*rulesets):
    return yaml.safe_dump({"rulesets": list(rulesets)}, sort_keys=False)


# A single-ruleset floor used by most main()-level fixtures below that do not need a second
# ruleset or the real floor's own shape.
_ONE_CONTEXT_FLOOR = _floor_yaml(_ruleset(rules=[{
    "type": "required_status_checks",
    "parameters": {"required_status_checks": [{"context": "check-branch", "integration_id": 15368}]},
}]))

# The real floor (PR 7's repository-floor.yml, captured in discovery): two rulesets, used for the
# "fully matches" / collect-all / pagination / extras-pass scenario below.
REAL_FLOOR_YAML = """\
rulesets:
  - name: process-gates
    target: branch
    enforcement: active
    conditions:
      ref_name:
        include:
          - "~DEFAULT_BRANCH"
        exclude: []
    bypass_actors: []
    rules:
      - type: required_status_checks
        parameters:
          required_status_checks:
            - context: check-branch
              integration_id: 15368
            - context: pr-title
              integration_id: 15368
            - context: repo-floor
              integration_id: 15368

  - name: pull-request
    target: branch
    enforcement: active
    conditions:
      ref_name:
        include:
          - "~DEFAULT_BRANCH"
        exclude: []
    bypass_actors:
      - actor_type: OrganizationAdmin
        actor_id: null
        bypass_mode: pull_request
    rules:
      - type: pull_request
        parameters:
          required_approving_review_count: 0
      - type: deletion
      - type: non_fast_forward
"""


def _contents_body(yaml_text, sha="deadbeef"):
    """GitHub's documented default (non-raw) shape for GET /repos/{o}/{r}/contents/{path}."""
    return json.dumps(
        {
            "name": FLOOR_PATH,
            "path": FLOOR_PATH,
            "sha": sha,
            "encoding": "base64",
            "content": base64.b64encode(yaml_text.encode()).decode(),
        }
    )


def _list_entry(ruleset_id, name, target="branch", enforcement="active", source_type="Repository",
                 source=REPO):
    return {
        "id": ruleset_id,
        "name": name,
        "target": target,
        "source_type": source_type,
        "source": source,
        "enforcement": enforcement,
        "node_id": "RRS_x",
        "_links": {"self": {"href": "x"}, "html": {"href": "x"}},
        "created_at": "2026-09-27T22:19:26.335-04:00",
        "updated_at": "2026-09-30T02:03:04.819-04:00",
    }


def _detail_body(ruleset_id, name, *, target="branch", enforcement="active", conditions=None,
                  rules=None, source_type="Repository", source=REPO):
    """The non-admin/workflow-token ruleset-detail shape (anon.json): no `bypass_actors`, no
    `current_user_can_bypass` key at all -- never an empty bypass list."""
    if conditions is None:
        conditions = {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}
    body = {
        "id": ruleset_id,
        "name": name,
        "target": target,
        "source_type": source_type,
        "source": source,
        "enforcement": enforcement,
        "conditions": conditions,
        "rules": rules or [],
        "node_id": "RRS_x",
        "created_at": "2026-09-27T22:19:26.335-04:00",
        "updated_at": "2026-09-30T02:03:04.819-04:00",
        "_links": {"self": {"href": "x"}, "html": {"href": "x"}},
    }
    return json.dumps(body)


class FakeAPI:
    """Stands in for repo-floor.py's `api_get`. Dispatches on the URL's own shape, so these tests
    do not also pin how repo-floor.py builds a URL out of
    GITHUB_API_URL/GITHUB_REPOSITORY/FLOOR_OWNER_REPO -- that construction is code-monkey's to
    choose. A call this fixture was not given a canned reply for raises, so a main() that calls
    the API in an order or combination a test did not expect fails loudly rather than silently
    returning something plausible.
    """

    def __init__(self):
        self.floor = None  # (status, headers, body_text) for the contents call
        self.list_pages = []  # consumed in call order by any call matching the list shape
        self.details = {}  # ruleset id -> (status, headers, body_text)
        self.calls = []

    def __call__(self, url, token):
        self.calls.append(url)
        if re.search(r"/contents/repository-floor\.yml", url):
            if self.floor is None:
                raise AssertionError(f"unexpected floor fetch: {url}")
            return self.floor
        match = re.search(r"/rulesets/(\d+)(?:\?|$)", url)
        if match:
            ruleset_id = int(match.group(1))
            if ruleset_id not in self.details:
                raise AssertionError(f"unexpected ruleset-detail call: {url}")
            return self.details[ruleset_id]
        if re.search(r"/rulesets(\?|$)", url):
            if not self.list_pages:
                raise AssertionError(f"unexpected rulesets-list call: {url}")
            assert "per_page=100" in url, f"rulesets-list call is missing per_page=100: {url}"
            return self.list_pages.pop(0)
        raise AssertionError(f"unexpected API call: {url}")


def _run(monkeypatch, fake, **env_kwargs):
    monkeypatch.setattr(rf, "api_get", fake)
    _env(monkeypatch, **env_kwargs)


def _expect_fail(monkeypatch, fake, **env_kwargs):
    _run(monkeypatch, fake, **env_kwargs)
    with pytest.raises(SystemExit) as exc_info:
        rf.main()
    return exc_info.value.code


def _expect_pass(monkeypatch, fake, **env_kwargs):
    _run(monkeypatch, fake, **env_kwargs)
    rf.main()  # must return, not raise


# Pure helpers: values_equal / _canonicalize, called directly with plain dicts and lists.


@pytest.mark.parametrize(
    "floor_value,live_value,expected",
    [
        (0, False, False),
        (0, 0, True),
        ([1], [True], False),
        ([1], [1], True),
        (15368.0, 15368, False),
        (15368, 15368, True),
    ],
    ids=["int-vs-bool", "int-vs-int", "list-int-vs-bool", "list-int-vs-int", "float-vs-int", "int-vs-int-2"],
)
def test_values_equal_is_type_strict(floor_value, live_value, expected):
    """0 != False, [1] != [True], and a float integration_id never equals the int GitHub sends --
    type-strict at every level, not only at the top."""
    assert rf.values_equal(floor_value, live_value) == expected


def test_compare_fields_null_floor_value_matches_a_live_key_present_and_null():
    assert rf.compare_fields("x", {"actor_id": None}, {"actor_id": None})


def test_compare_fields_null_floor_value_fails_against_an_absent_live_key():
    """An absent live key is a shortfall, never treated as an implicit null."""
    assert not rf.compare_fields("x", {"actor_id": None}, {})


def test_values_equal_generic_list_with_one_extra_live_element_fails():
    """Unlike required_status_checks's own subset match, every other list must be equal as a
    set -- one extra live element fails it."""
    assert not rf.values_equal(["a", "b"], ["a", "b", "c"])


def test_values_equal_generic_list_is_order_independent():
    assert rf.values_equal(["a", "b"], ["b", "a"])


def test_values_equal_list_of_mappings_compares_as_a_set():
    """Order carries no meaning at either nesting level: the list's own order, and each mapping's
    own key order."""
    floor = [{"tool": "CodeQL", "alerts_threshold": "errors"}, {"tool": "Snyk Code", "alerts_threshold": "all"}]
    live = [{"alerts_threshold": "all", "tool": "Snyk Code"}, {"tool": "CodeQL", "alerts_threshold": "errors"}]
    assert rf.values_equal(floor, live)


def test_values_equal_list_of_mappings_mismatch_fails():
    floor = [{"tool": "CodeQL", "alerts_threshold": "errors"}]
    live = [{"tool": "CodeQL", "alerts_threshold": "all"}]
    assert not rf.values_equal(floor, live)


def test_required_status_checks_floor_entry_matches_among_extra_live_entries():
    """required_status_checks allows extra live entries the floor does not name."""
    floor = [{"context": "check-branch"}]
    live = [{"context": "check-branch"}, {"context": "extra"}]
    assert rf.values_equal(floor, live, key="required_status_checks")


def test_required_status_checks_unknown_key_on_floor_entry_never_matches():
    """An unknown key on a floor entry can never be satisfied -- it is compared exactly like
    every other field on the entry, not ignored."""
    floor = [{"context": "check-branch", "bogus": 1}]
    live = [{"context": "check-branch"}]
    assert not rf.values_equal(floor, live, key="required_status_checks")


def test_required_status_checks_integration_id_mismatch_fails():
    floor = [{"context": "check-branch", "integration_id": 15368}]
    live = [{"context": "check-branch", "integration_id": 1}]
    assert not rf.values_equal(floor, live, key="required_status_checks")


def test_required_status_checks_integration_id_required_but_absent_live_fails():
    """The floor's context carries no integration_id key, so live must carry none either -- a
    present integration_id of any value fails it, not only a differing one."""
    floor = [{"context": "check-branch"}]
    live = [{"context": "check-branch", "integration_id": 15368}]
    assert not rf.values_equal(floor, live, key="required_status_checks")


def test_required_status_checks_integration_id_both_absent_passes():
    floor = [{"context": "check-branch"}]
    live = [{"context": "check-branch"}]
    assert rf.values_equal(floor, live, key="required_status_checks")


def test_compare_fields_shortfall_names_the_full_key_path(capsys):
    """A nested mismatch is reported by its full key path, not only the leaf key -- this is what
    lets strict_required_status_checks_policy be told apart from any other field that mismatches
    the same way."""
    ok = rf.compare_fields(
        "process-gates",
        {"required_status_checks": {"strict_required_status_checks_policy": True}},
        {"required_status_checks": {"strict_required_status_checks_policy": False}},
    )

    assert not ok
    err = capsys.readouterr().err
    assert (
        "repo-floor: shortfall: process-gates: "
        "required_status_checks.strict_required_status_checks_policy: floor True, repository False"
        in err
    )


def test_compare_fields_matching_nested_value_passes():
    assert rf.compare_fields(
        "process-gates",
        {"required_status_checks": {"strict_required_status_checks_policy": True}},
        {"required_status_checks": {"strict_required_status_checks_policy": True}},
    )


# compare_ruleset: wiring from a ruleset entry down into its own fields and its rules' parameters.


def test_compare_ruleset_target_mismatch_is_a_shortfall(capsys):
    floor_entry = _ruleset(target="branch")
    live = {"target": "tag", "enforcement": "active", "conditions": floor_entry["conditions"], "rules": []}

    ok = rf.compare_ruleset("process-gates", floor_entry, live)

    assert not ok
    assert "process-gates: target: floor branch, repository tag" in capsys.readouterr().err


def test_compare_ruleset_matching_target_passes():
    floor_entry = _ruleset(target="branch")
    live = {"target": "branch", "enforcement": "active", "conditions": floor_entry["conditions"], "rules": []}

    assert rf.compare_ruleset("process-gates", floor_entry, live)


def test_compare_ruleset_enforcement_mismatch_is_a_shortfall(capsys):
    """A seeded typo ("actve") is not a real enforcement value; no live value can ever satisfy
    it -- fail-closed, no vocabulary list needed."""
    floor_entry = _ruleset(enforcement="actve")
    live = {"target": "branch", "enforcement": "active", "conditions": floor_entry["conditions"], "rules": []}

    ok = rf.compare_ruleset("pull-request", floor_entry, live)

    assert not ok
    assert "repo-floor: shortfall: pull-request: enforcement: floor actve, repository active" in capsys.readouterr().err


def test_compare_ruleset_rule_type_with_no_live_match_is_a_shortfall(capsys):
    """A floor rule type no live rule carries -- "non_fast_forwards" (plural) is not a real rule
    type -- is reported as missing, never satisfied by coincidence."""
    floor_entry = _ruleset(rules=[{"type": "non_fast_forwards"}])
    live = {"target": "branch", "enforcement": "active", "conditions": floor_entry["conditions"],
            "rules": [{"type": "non_fast_forward"}]}

    ok = rf.compare_ruleset("pull-request", floor_entry, live)

    assert not ok
    err = capsys.readouterr().err
    assert "pull-request" in err
    assert "non_fast_forwards: missing" in err


def test_compare_ruleset_unknown_parameter_key_never_matches(capsys):
    """A bogus parameter key the live rule's parameters do not carry can never be satisfied."""
    floor_entry = _ruleset(rules=[{
        "type": "pull_request",
        "parameters": {"required_approving_review_count": 0, "bogus_key": 1},
    }])
    live = {"target": "branch", "enforcement": "active", "conditions": floor_entry["conditions"],
            "rules": [{"type": "pull_request", "parameters": {"required_approving_review_count": 0}}]}

    ok = rf.compare_ruleset("pull-request", floor_entry, live)

    assert not ok
    assert "pull_request.bogus_key: floor 1, repository missing" in capsys.readouterr().err


def test_compare_ruleset_plumbs_a_rule_parameter_list_of_mappings(capsys):
    """Wiring: compare_ruleset reaches a rule's own parameters, which have their own
    list-of-mappings set-comparison (values_equal's own contract, proven above)."""
    floor_entry = _ruleset(rules=[{
        "type": "code_scanning",
        "parameters": {"code_scanning_tools": [{"tool": "CodeQL", "alerts_threshold": "errors"}]},
    }])
    live = {"target": "branch", "enforcement": "active", "conditions": floor_entry["conditions"],
            "rules": [{"type": "code_scanning",
                       "parameters": {"code_scanning_tools": [{"tool": "CodeQL", "alerts_threshold": "all"}]}}]}

    ok = rf.compare_ruleset("process-gates", floor_entry, live)

    assert not ok
    assert "code_scanning.code_scanning_tools" in capsys.readouterr().err


def test_compare_ruleset_plumbs_a_ruleset_level_list_of_mappings(capsys):
    """Wiring: compare_ruleset reaches a ruleset's own top-level fields (conditions), which carry
    the same list-of-mappings set-comparison a rule's parameters do."""
    floor_entry = _ruleset(conditions={
        "repository_property": {"include": [{"name": "team", "property_values": ["platform"]}], "exclude": []}
    })
    live = {"target": "branch", "enforcement": "active",
            "conditions": {"repository_property": {
                "include": [{"name": "team", "property_values": ["other"]}], "exclude": []}},
            "rules": []}

    ok = rf.compare_ruleset("process-gates", floor_entry, live)

    assert not ok
    assert "conditions.repository_property" in capsys.readouterr().err


# Full pass: exact match, pagination, extras, org-sourced ruleset counting by name, both floor
# rulesets' bypass reported "not verified" -- consolidated to keep the fixture budget down; each
# property otherwise has its own direct-helper test above or its own main()-level test below.


def test_full_floor_matches_passes_with_pagination_extras_and_org_source(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(REAL_FLOOR_YAML))

    next_url = f"{API_URL}/repos/{REPO}/rulesets?per_page=100&page=2"
    # Page 1: an extra ruleset the floor does not name, plus "process-gates".
    fake.list_pages = [
        (
            200,
            _headers(link=f'<{next_url}>; rel="next"'),
            json.dumps(
                [
                    _list_entry(24094525, "tag immutability", target="tag"),
                    _list_entry(1001, "process-gates"),
                ]
            ),
        ),
        # Page 2 (no Link header -- pagination stops here): "pull-request", sourced from the
        # organization rather than the repository (counts by name regardless of source).
        (200, _headers(), json.dumps([_list_entry(1002, "pull-request", source_type="Organization",
                                                    source="WisewareOrg")])),
    ]
    fake.details = {
        24094525: (200, _headers(), _detail_body(24094525, "tag immutability", target="tag",
                                                   rules=[{"type": "update"}, {"type": "deletion"}])),
        1001: (
            200,
            _headers(),
            _detail_body(
                1001,
                "process-gates",
                rules=[
                    # An extra rule type the floor does not list.
                    {"type": "required_linear_history"},
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": "check-branch", "integration_id": 15368},
                                {"context": "pr-title", "integration_id": 15368},
                                {"context": "repo-floor", "integration_id": 15368},
                                # An extra context the floor does not list.
                                {"context": "coverage", "integration_id": 15368},
                            ]
                        },
                    },
                ],
            ),
        ),
        1002: (
            200,
            _headers(),
            _detail_body(
                1002,
                "pull-request",
                source_type="Organization",
                source="WisewareOrg",
                rules=[
                    {"type": "pull_request", "parameters": {"required_approving_review_count": 0}},
                    {"type": "deletion"},
                    {"type": "non_fast_forward"},
                ],
            ),
        ),
    }

    _expect_pass(monkeypatch, fake)

    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert "repo-floor: repository meets the floor" in out
    assert "repo-floor: shortfall:" not in err
    assert "repo-floor: broken:" not in err
    assert "repo-floor: bypass not verified: process-gates" in err
    assert "repo-floor: bypass not verified: pull-request" in err
    # The non-floor-named extra ruleset gets no bypass line: bypass is reported only for a floor
    # ruleset found live.
    assert "tag immutability" not in err


# Ruleset-name matching: missing, case-differing, and ambiguous (duplicate live names) -- only
# main() does this, by walking live_entries, so it cannot be tested at compare_ruleset's level.


def test_floor_named_ruleset_entirely_absent_live_is_a_shortfall_not_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(9999, "something-else")]))]
    fake.details = {}

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates" in captured
    assert "repository missing" in captured
    assert "repo-floor: broken:" not in captured


def test_ruleset_name_differing_only_by_case_is_a_shortfall(monkeypatch, capsys):
    """Matching is exact and case-sensitive -- a live ruleset named with different case is not the
    same ruleset and is reported the same way a wholly absent one is."""
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "Process-Gates")]))]
    fake.details = {1001: (200, _headers(), _detail_body(1001, "Process-Gates", rules=[]))}

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates" in captured
    assert "repository missing" in captured


def test_duplicate_live_ruleset_names_are_an_ambiguous_shortfall(monkeypatch, capsys):
    """Both duplicates are built to otherwise fully satisfy the floor, so this can only be caught
    by an implementation that actually detects two live rulesets sharing the floor name -- an
    implementation that just takes the first match would wrongly pass."""
    live_rules = [{"type": "required_status_checks",
                   "parameters": {"required_status_checks": [{"context": "check-branch", "integration_id": 15368}]}}]
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [
        (200, _headers(), json.dumps([_list_entry(1001, "process-gates"), _list_entry(1002, "process-gates")]))
    ]
    fake.details = {
        1001: (200, _headers(), _detail_body(1001, "process-gates", rules=live_rules)),
        1002: (200, _headers(), _detail_body(1002, "process-gates", rules=live_rules)),
    }

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates" in captured
    assert "ambiguous" in captured
    assert "repo-floor: broken:" not in captured


# collect-all: every shortfall is printed, not only the first.


def test_multiple_shortfalls_across_rulesets_are_all_reported(monkeypatch, capsys):
    # process-gates: missing the required context entirely. pull-request: enforcement mismatch.
    floor = _floor_yaml(
        _ruleset(rules=[{"type": "required_status_checks",
                          "parameters": {"required_status_checks": [{"context": "check-branch"}]}}]),
        _ruleset(name="pull-request", rules=[{"type": "deletion"}]),
    )
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(floor))
    fake.list_pages = [
        (200, _headers(), json.dumps([_list_entry(1001, "process-gates"), _list_entry(1002, "pull-request")]))
    ]
    fake.details = {
        1001: (200, _headers(), _detail_body(1001, "process-gates", rules=[
            {"type": "required_status_checks", "parameters": {"required_status_checks": []}}
        ])),
        1002: (200, _headers(), _detail_body(1002, "pull-request", enforcement="disabled",
                                              rules=[{"type": "deletion"}])),
    }

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall: process-gates:" in captured
    assert "repo-floor: shortfall: pull-request: enforcement: floor active, repository disabled" in captured


# Read failures: broken, never a shortfall, never a pass -- on any call, including a malformed
# (but syntactically-200) response body at any of the three read sites.


@pytest.mark.parametrize("status", [404, 403, 429, 500])
def test_floor_fetch_http_error_is_broken(monkeypatch, capsys, status):
    fake = FakeAPI()
    fake.floor = (status, _headers(), "")

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr()
    assert "repo-floor: broken:" in captured.err
    assert "repo-floor: shortfall:" not in captured.err
    assert "repo-floor: repository meets the floor" not in captured.out


def test_floor_unparseable_yaml_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body("rulesets: [this is not: valid: yaml"))

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr()
    assert "repo-floor: broken:" in captured.err
    assert "repo-floor: shortfall:" not in captured.err


def test_floor_contents_non_json_body_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), "not json at all")

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr()
    assert "repo-floor: broken:" in captured.err
    assert "repo-floor: shortfall:" not in captured.err


def test_floor_contents_json_list_body_is_broken(monkeypatch, capsys):
    """A JSON list where the contents envelope's own mapping (with its `content` field) is
    expected."""
    fake = FakeAPI()
    fake.floor = (200, _headers(), json.dumps([1, 2, 3]))

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    assert "repo-floor: broken:" in capsys.readouterr().err


def test_rulesets_list_fetch_failure_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [(404, _headers(), "")]

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: broken:" in captured
    assert "repo-floor: shortfall:" not in captured


def test_rulesets_list_non_json_body_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [(200, _headers(), "not json at all")]

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    assert "repo-floor: broken:" in capsys.readouterr().err


def test_ruleset_detail_fetch_failure_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "process-gates")]))]
    fake.details = {1001: (500, _headers(), "")}

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: broken:" in captured
    assert "repo-floor: shortfall:" not in captured


def test_ruleset_detail_non_json_body_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "process-gates")]))]
    fake.details = {1001: (200, _headers(), "not json at all")}

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    assert "repo-floor: broken:" in capsys.readouterr().err


# Floor-shape faults: validate_floor_shape is pure, so every case but one calls it directly; the
# last proves main() actually wires it in, before any API call beyond the floor fetch itself.

_SHAPE_FAULTS = {
    "not_a_mapping": "- just\n- a\n- list\n",
    "no_rulesets_key": "other_key: 1\n",
    "rulesets_empty": "rulesets: []\n",
    "rulesets_not_a_list": "rulesets: {}\n",
    "entry_without_name": "rulesets:\n  - target: branch\n    enforcement: active\n    rules: []\n",
    "ruleset_name_not_a_string": (
        "rulesets:\n  - name: 123\n    target: branch\n    enforcement: active\n    rules: []\n"
    ),
    "rule_without_type": (
        "rulesets:\n  - name: x\n    target: branch\n    enforcement: active\n"
        "    rules:\n      - parameters: {}\n"
    ),
    "rule_type_not_a_string": (
        "rulesets:\n  - name: x\n    target: branch\n    enforcement: active\n"
        "    rules:\n      - type: 123\n"
    ),
    "required_status_checks_entry_not_a_mapping": (
        "rulesets:\n  - name: x\n    target: branch\n    enforcement: active\n"
        "    rules:\n      - type: required_status_checks\n        parameters:\n"
        "          required_status_checks:\n            - just-a-string\n"
    ),
    "duplicate_ruleset_names": (
        "rulesets:\n"
        "  - name: x\n    target: branch\n    enforcement: active\n    rules: []\n"
        "  - name: x\n    target: branch\n    enforcement: active\n    rules: []\n"
    ),
    "duplicate_rule_types": (
        "rulesets:\n  - name: x\n    target: branch\n    enforcement: active\n"
        "    rules:\n      - type: deletion\n      - type: deletion\n"
    ),
}


@pytest.mark.parametrize("fault", list(_SHAPE_FAULTS), ids=list(_SHAPE_FAULTS))
def test_floor_shape_fault_is_broken(fault):
    with pytest.raises(SystemExit) as exc_info:
        rf.validate_floor_shape(yaml.safe_load(_SHAPE_FAULTS[fault]))

    assert exc_info.value.code == 1


def test_floor_shape_fault_is_broken_through_the_full_pipeline(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_SHAPE_FAULTS["not_a_mapping"]))

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr()
    assert "repo-floor: broken:" in captured.err
    assert "repo-floor: shortfall:" not in captured.err
    assert "repo-floor: repository meets the floor" not in captured.out


# Floor ref selection: WisewareOrg/.github's own pull_request reads the PR head, every other case
# reads "main" -- keyed on the repository, not generically on the event name. Each case fails the
# floor fetch itself (a deliberate 404) after it is made, since only the requested URL matters.


@pytest.mark.parametrize(
    "repository,event_name,pr_head_sha,expected_ref",
    [
        (FLOOR_OWNER_REPO, "pull_request", "abc123sha", "abc123sha"),
        (FLOOR_OWNER_REPO, "push", None, "main"),
        (REPO, "pull_request", "abc123sha", "main"),
        ("WISEWAREORG/.GITHUB", "pull_request", "abc123sha", "abc123sha"),
    ],
)
def test_floor_ref_selection(monkeypatch, repository, event_name, pr_head_sha, expected_ref):
    fake = FakeAPI()
    fake.floor = (404, _headers(), "")

    _expect_fail(monkeypatch, fake, repository=repository, event_name=event_name, pr_head_sha=pr_head_sha)

    floor_calls = [url for url in fake.calls if "repository-floor.yml" in url]
    assert len(floor_calls) == 1
    assert f"ref={expected_ref}" in floor_calls[0]


# api_get itself: its own branches, patching urllib.request.urlopen (not api_get).


class _FakeHTTPResponse:
    def __init__(self, status, body_text, headers=None):
        self.status = status
        self.headers = headers if headers is not None else Message()
        self._body = body_text.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_api_get_200_returns_status_headers_and_the_raw_unparsed_body(monkeypatch):
    def fake_urlopen(_request):
        return _FakeHTTPResponse(200, '{"not": "parsed"}', headers=_headers(link='<x>; rel="next"'))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    status, headers, body = rf.api_get("https://api.github.com/repos/x/y", "")

    assert status == 200
    assert body == '{"not": "parsed"}'  # api_get does not parse JSON; callers do
    assert headers.get("link") == '<x>; rel="next"'  # case-insensitive, like the real headers object


def test_api_get_http_error_returns_its_status_code(monkeypatch):
    def fake_urlopen(request):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    status, _headers_, _body = rf.api_get("https://api.github.com/repos/x/y", "")

    assert status == 404


def test_api_get_url_error_exits_broken_without_a_shortfall_tag(monkeypatch, capsys):
    def fake_urlopen(_request):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit) as exc_info:
        rf.api_get("https://api.github.com/repos/x/y", "")

    assert exc_info.value.code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: broken:" in captured
    assert "cannot reach" in captured
    assert "shortfall" not in captured


def test_api_get_sends_authorization_only_with_a_token(monkeypatch):
    requests_seen = []

    def fake_urlopen(request):
        requests_seen.append(request)
        return _FakeHTTPResponse(200, "{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    rf.api_get("https://api.github.com/repos/x/y", "")
    rf.api_get("https://api.github.com/repos/x/y", TOKEN)

    assert "Authorization" not in requests_seen[0].headers
    assert requests_seen[1].headers.get("Authorization") == f"Bearer {TOKEN}"


# __main__ guard -- coverage for `sys.exit(main())`, without a pragma.


def test_dunder_main_guard_runs_main_and_exits(monkeypatch):
    """Runs the script the way the action does. Every call fails at the transport level (URLError),
    so this needs no per-module `api_get` patch of its own freshly executed module instance."""
    _env(monkeypatch)

    def fake_urlopen(_request):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert exc_info.value.code == 1
