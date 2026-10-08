"""Specifies repo-floor/repo-floor.py: compares a calling repository's live GitHub rulesets
against the floor stated once in WisewareOrg/.github's repository-floor.yml (PROCESS.md PROC-011),
per the issue-26 plan's rulings R1-R12 and completeness-read resolutions H1-H14.

`api_get(url, token) -> (status, headers, body_text)` is the one module-level seam (H1): a
single-page GitHub REST fetch, unparsed body, returning the same `headers` object urllib hands
back (an `email.message.Message`/`http.client.HTTPMessage`, case-insensitively keyed) so a test
double built on it does not pin which case the implementation queries a header by. Every
main()-level test below replaces `api_get` with a `FakeAPI` that dispatches on the URL's own shape
-- the floor's contents endpoint, the rulesets list endpoint (paginated via `Link`), or a single
ruleset's detail endpoint -- the same "dispatch on shape, not the literal URL" discipline
check-branch/tests/test_check_branch.py uses, so these tests do not also pin how repo-floor.py
builds a URL out of GITHUB_API_URL/GITHUB_REPOSITORY. `api_get`'s own branches are tested
separately at the bottom, patching `urllib.request.urlopen` instead (check-branch's pattern).

Ruleset list entries carry no `rules`/`conditions` (GitHub's own list-endpoint shape, list.json);
only a ruleset's detail endpoint does, and matches the non-admin/workflow-token shape captured in
discovery (anon.json): no `bypass_actors`, no `current_user_can_bypass` key at all -- the shape
`repo-floor` actually receives from a `GITHUB_TOKEN` run, per R7/H11.

Two things the plan's H1-H14 leave open, where a full-string assertion would pin an unspecified
rendering rather than the stated requirement:
- H2's `<field or rule>` token for a floor-named ruleset entirely absent from the live list (no
  sub-field exists to name there) and for a rule missing entirely (named in the issue body as "the
  missing or differing rule", which only commits to the rule's own identity, not a stringified
  "floor <x>" value for a presence/absence fact). These assertions check the determined parts
  (prefix, ruleset name, rule/field name where it is the rule's own `type`, and the literal
  "missing" substitution) and do not pin a full contiguous line.
- The literal rendering of a non-scalar `floor <x>, repository <y>` pair (a dict-valued
  `parameters` or `conditions`, or a required-status-check entry). Scalar-string fields
  (`enforcement`, `target`) get full-line assertions instead, since R1 names them directly and a
  string value has no ambiguous stringification.

Judgment call, not escalated: the floor is fetched via the REST contents API (W1) with the one
fixed header set `api_get` sends for every call (H1 names no per-call header override), so its
response is GitHub's documented default shape -- a JSON envelope with a base64 `content` field --
rather than a raw-media-type body. This is GitHub's own documented API behaviour for that endpoint
under a default Accept header, not a contract invented for this test, but it governs every floor
fixture below and is worth a reviewer's second look.
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

SCRIPT = Path(__file__).resolve().parents[1] / "repo-floor.py"

API_URL = "https://api.github.com"
REPO = "WisewareOrg/wise-ci"
TOKEN = "test-token-xyz789"  # noqa: S105 -- a fixture value, never a real credential

FLOOR_OWNER_REPO = "WisewareOrg/.github"
FLOOR_PATH = "repository-floor.yml"

# The real floor (PR 7's repository-floor.yml, captured in discovery): two rulesets, used for the
# "fully matches" / collect-all / pagination / extras-pass scenarios below. Smaller, single-purpose
# floors are built inline for the narrower fault-seeding tests, per docs/TESTING.md's "a test
# creates its defective input on the fly".
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
    """Stands in for repo-floor.py's `api_get`. Dispatches on the URL's own shape, exactly as
    check-branch/tests/test_check_branch.py's FakeAPI does, so these tests do not also pin how
    repo-floor.py builds a URL out of GITHUB_API_URL/GITHUB_REPOSITORY/FLOOR_OWNER_REPO -- that
    construction is code-monkey's to choose. A call this fixture was not given a canned reply for
    raises, so a main() that calls the API in an order or combination a test did not expect fails
    loudly rather than silently returning something plausible.
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


def _no_api_call(*_args, **_kwargs):
    raise AssertionError("api_get must not be called")


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


# ---------------------------------------------------------------------------------------------
# Full pass: exact match, pagination, extras (R2), an organization-sourced ruleset counting by
# name (H5), both floor rulesets' bypass reported "not verified" despite the floor itself naming
# bypass_actors for "pull-request" (R7) -- consolidated into one scenario to keep the fixture
# budget down; each property still has its own assertion below.
# ---------------------------------------------------------------------------------------------


def test_full_floor_matches_passes_with_pagination_extras_and_org_source(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(REAL_FLOOR_YAML))

    next_url = f"{API_URL}/repos/{REPO}/rulesets?per_page=100&page=2"
    # Page 1: an extra ruleset the floor does not name (R2 extras) plus "process-gates".
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
        # organization rather than the repository (H5: counts by name regardless of source).
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
                    # An extra rule type the floor does not list (R2 extras).
                    {"type": "required_linear_history"},
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": "check-branch", "integration_id": 15368},
                                {"context": "pr-title", "integration_id": 15368},
                                {"context": "repo-floor", "integration_id": 15368},
                                # An extra context the floor does not list (R2 extras).
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
    # ruleset found live (H2).
    assert "tag immutability" not in err


# ---------------------------------------------------------------------------------------------
# required_status_checks' integration_id, both directions (R5)
# ---------------------------------------------------------------------------------------------

_ONE_CONTEXT_FLOOR = """\
rulesets:
  - name: process-gates
    target: branch
    enforcement: active
    conditions:
      ref_name:
        include: ["~DEFAULT_BRANCH"]
        exclude: []
    bypass_actors: []
    rules:
      - type: required_status_checks
        parameters:
          required_status_checks:
            - context: check-branch
              integration_id: 15368
"""

_ONE_CONTEXT_FLOOR_NO_ID = """\
rulesets:
  - name: process-gates
    target: branch
    enforcement: active
    conditions:
      ref_name:
        include: ["~DEFAULT_BRANCH"]
        exclude: []
    bypass_actors: []
    rules:
      - type: required_status_checks
        parameters:
          required_status_checks:
            - context: check-branch
"""


def _single_ruleset_fake(floor_yaml, live_rules):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(floor_yaml))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "process-gates")]))]
    fake.details = {1001: (200, _headers(), _detail_body(1001, "process-gates", rules=live_rules))}
    return fake


def test_integration_id_mismatch_is_a_shortfall(monkeypatch, capsys):
    live_rules = [
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": "check-branch", "integration_id": 1}]},
        }
    ]
    fake = _single_ruleset_fake(_ONE_CONTEXT_FLOOR, live_rules)

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates" in captured
    assert "required_status_checks" in captured


def test_integration_id_required_absent_but_present_live_is_a_shortfall(monkeypatch, capsys):
    """R5: the floor's context carries no integration_id key, so live must carry none either --
    a present integration_id of any value fails it, not only a differing one."""
    live_rules = [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": "check-branch", "integration_id": 15368}]
            },
        }
    ]
    fake = _single_ruleset_fake(_ONE_CONTEXT_FLOOR_NO_ID, live_rules)

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates" in captured


def test_integration_id_both_absent_passes(monkeypatch):
    live_rules = [
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": "check-branch"}]},
        }
    ]
    fake = _single_ruleset_fake(_ONE_CONTEXT_FLOOR_NO_ID, live_rules)

    _expect_pass(monkeypatch, fake)


# ---------------------------------------------------------------------------------------------
# required_status_checks' OTHER parameters (R1): every field the floor lists for a
# required_status_checks rule must equal live exactly -- not only the required_status_checks
# contexts list itself, which has its own subset-matched handling (R5) one branch up.
# ---------------------------------------------------------------------------------------------

_STRICT_POLICY_FLOOR = """\
rulesets:
  - name: process-gates
    target: branch
    enforcement: active
    conditions:
      ref_name:
        include: ["~DEFAULT_BRANCH"]
        exclude: []
    bypass_actors: []
    rules:
      - type: required_status_checks
        parameters:
          strict_required_status_checks_policy: true
          required_status_checks:
            - context: check-branch
"""


def test_required_status_checks_other_parameter_mismatch_is_a_shortfall(monkeypatch, capsys):
    """R1: strict_required_status_checks_policy is a required_status_checks parameter like any
    other -- a differing value is a shortfall even though the required_status_checks contexts list
    itself fully matches."""
    live_rules = [
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": False,
                "required_status_checks": [{"context": "check-branch"}],
            },
        }
    ]
    fake = _single_ruleset_fake(_STRICT_POLICY_FLOOR, live_rules)

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates: required_status_checks: floor True, repository False" in captured


def test_required_status_checks_other_parameter_matching_passes(monkeypatch):
    """Same contract, the other direction: a matching strict_required_status_checks_policy value
    alongside a matching required_status_checks contexts list passes."""
    live_rules = [
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": "check-branch"}],
            },
        }
    ]
    fake = _single_ruleset_fake(_STRICT_POLICY_FLOOR, live_rules)

    _expect_pass(monkeypatch, fake)


# ---------------------------------------------------------------------------------------------
# Lists of mappings compared as sets (H3), for a rule parameter other than
# required_status_checks.required_status_checks: a code_scanning rule's code_scanning_tools
# (real shape -- each tool a mapping of scalar fields, so _canonicalize's dict branch recurses
# into the list's own elements).
# ---------------------------------------------------------------------------------------------

_CODE_SCANNING_FLOOR = """\
rulesets:
  - name: process-gates
    target: branch
    enforcement: active
    conditions:
      ref_name:
        include: ["~DEFAULT_BRANCH"]
        exclude: []
    bypass_actors: []
    rules:
      - type: code_scanning
        parameters:
          code_scanning_tools:
            - tool: CodeQL
              alerts_threshold: errors
              security_alerts_threshold: high_or_higher
            - tool: Snyk Code
              alerts_threshold: all
              security_alerts_threshold: all
"""


def test_code_scanning_tools_mismatch_is_a_shortfall(monkeypatch, capsys):
    """A changed tool threshold can never be satisfied by the live set, regardless of order."""
    live_rules = [
        {
            "type": "code_scanning",
            "parameters": {
                "code_scanning_tools": [
                    {"tool": "CodeQL", "alerts_threshold": "all", "security_alerts_threshold": "high_or_higher"},
                    {"tool": "Snyk Code", "alerts_threshold": "all", "security_alerts_threshold": "all"},
                ]
            },
        }
    ]
    fake = _single_ruleset_fake(_CODE_SCANNING_FLOOR, live_rules)

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates" in captured
    assert "code_scanning" in captured


def test_code_scanning_tools_reordered_list_of_mappings_passes(monkeypatch):
    """Same contract, the other direction: code_scanning_tools' own order carries no meaning (H3)
    -- the same two mappings in the opposite order, and with one mapping's own fields reordered
    too, still passes."""
    live_rules = [
        {
            "type": "code_scanning",
            "parameters": {
                "code_scanning_tools": [
                    {"tool": "Snyk Code", "alerts_threshold": "all", "security_alerts_threshold": "all"},
                    {"security_alerts_threshold": "high_or_higher", "tool": "CodeQL", "alerts_threshold": "errors"},
                ]
            },
        }
    ]
    fake = _single_ruleset_fake(_CODE_SCANNING_FLOOR, live_rules)

    _expect_pass(monkeypatch, fake)


# ---------------------------------------------------------------------------------------------
# Lists of mappings compared as sets (H3), nested case: a repository_property ruleset condition's
# include/exclude entries are themselves a list of mappings, and each mapping's own
# property_values is a list too (real shape) -- _canonicalize's dict branch recurses into a
# list-valued field of its own, not only a scalar one.
# ---------------------------------------------------------------------------------------------

_REPO_PROPERTY_FLOOR = """\
rulesets:
  - name: process-gates
    target: branch
    enforcement: active
    conditions:
      repository_property:
        include:
          - name: environment
            property_values: ["production", "staging"]
          - name: team
            property_values: ["platform"]
        exclude: []
    bypass_actors: []
    rules: []
"""


def _repo_property_conditions(environment_values, team_values=("platform",), order=("environment", "team")):
    entries = {
        "environment": {"name": "environment", "property_values": list(environment_values)},
        "team": {"name": "team", "property_values": list(team_values)},
    }
    return {"repository_property": {"include": [entries[key] for key in order], "exclude": []}}


def test_repository_property_values_mismatch_is_a_shortfall(monkeypatch, capsys):
    """A changed property value can never be satisfied by the live set, regardless of order at
    either nesting level."""
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_REPO_PROPERTY_FLOOR))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "process-gates")]))]
    live_conditions = _repo_property_conditions(["production", "qa"])  # "qa" instead of "staging"
    fake.details = {
        1001: (200, _headers(), _detail_body(1001, "process-gates", conditions=live_conditions, rules=[]))
    }

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "process-gates" in captured
    assert "conditions" in captured


def test_repository_property_reordered_list_of_mappings_and_nested_list_passes(monkeypatch):
    """Same contract, the other direction: the include list's own order and each entry's
    property_values order both carry no meaning (H3) -- reordering both still passes."""
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_REPO_PROPERTY_FLOOR))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "process-gates")]))]
    live_conditions = _repo_property_conditions(["staging", "production"], order=("team", "environment"))
    fake.details = {
        1001: (200, _headers(), _detail_body(1001, "process-gates", conditions=live_conditions, rules=[]))
    }

    _expect_pass(monkeypatch, fake)


# ---------------------------------------------------------------------------------------------
# Seeded typos (R6: fail-closed, no vocabulary list -- a typo cannot equal any live value)
# ---------------------------------------------------------------------------------------------


def test_seeded_rule_type_typo_non_fast_forwards_never_matches(monkeypatch, capsys):
    """"non_fast_forwards" (plural) is not a real rule type; no live rule can ever carry it, so
    the floor rule can never be satisfied -- fails as a missing rule, never as a pass."""
    floor = """\
rulesets:
  - name: pull-request
    target: branch
    enforcement: active
    conditions:
      ref_name: {include: ["~DEFAULT_BRANCH"], exclude: []}
    bypass_actors: []
    rules:
      - type: non_fast_forwards
"""
    live_rules = [{"type": "non_fast_forward"}]
    fake = _single_ruleset_fake(floor, live_rules)
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "pull-request")]))]
    fake.details = {1001: (200, _headers(), _detail_body(1001, "pull-request", rules=live_rules))}

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "pull-request" in captured
    assert "non_fast_forwards" in captured
    assert "missing" in captured


def test_seeded_enforcement_typo_actve_never_matches(monkeypatch, capsys):
    """"actve" is not a real enforcement value; `enforcement` is a scalar string, so the full
    shortfall line is fully determined (R1 names `enforcement` directly)."""
    floor = """\
rulesets:
  - name: pull-request
    target: branch
    enforcement: actve
    conditions:
      ref_name: {include: ["~DEFAULT_BRANCH"], exclude: []}
    bypass_actors: []
    rules: []
"""
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(floor))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "pull-request")]))]
    fake.details = {1001: (200, _headers(), _detail_body(1001, "pull-request", rules=[]))}

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall: pull-request: enforcement: floor actve, repository active" in captured


def test_seeded_unknown_parameter_key_never_matches(monkeypatch, capsys):
    """A bogus parameter key the live rule's parameters do not carry can never be satisfied."""
    floor = """\
rulesets:
  - name: pull-request
    target: branch
    enforcement: active
    conditions:
      ref_name: {include: ["~DEFAULT_BRANCH"], exclude: []}
    bypass_actors: []
    rules:
      - type: pull_request
        parameters:
          required_approving_review_count: 0
          bogus_key: 1
"""
    live_rules = [{"type": "pull_request", "parameters": {"required_approving_review_count": 0}}]
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(floor))
    fake.list_pages = [(200, _headers(), json.dumps([_list_entry(1001, "pull-request")]))]
    fake.details = {1001: (200, _headers(), _detail_body(1001, "pull-request", rules=live_rules))}

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: shortfall:" in captured
    assert "pull-request" in captured
    assert "pull_request" in captured


# ---------------------------------------------------------------------------------------------
# Ruleset-name matching (R3): missing, case-differing, and ambiguous (duplicate live names)
# ---------------------------------------------------------------------------------------------


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
    """R3: matching is exact and case-sensitive -- a live ruleset named with different case is not
    the same ruleset and is reported the same way a wholly absent one is."""
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


# ---------------------------------------------------------------------------------------------
# collect-all (H2): every shortfall is printed, not only the first
# ---------------------------------------------------------------------------------------------


def test_multiple_shortfalls_across_rulesets_are_all_reported(monkeypatch, capsys):
    floor = _ONE_CONTEXT_FLOOR + """\
  - name: pull-request
    target: branch
    enforcement: active
    conditions:
      ref_name: {include: ["~DEFAULT_BRANCH"], exclude: []}
    bypass_actors: []
    rules:
      - type: deletion
"""
    # process-gates: missing the required context entirely. pull-request: enforcement mismatch.
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


# ---------------------------------------------------------------------------------------------
# Read failures (R9/H5): broken, never a shortfall, never a pass -- "on any call"
# ---------------------------------------------------------------------------------------------


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


def test_floor_fetch_network_error_is_broken(monkeypatch, capsys):
    def fake_api_get(_url, _token):
        raise urllib.error.URLError("boom")

    code = _expect_fail(monkeypatch, fake_api_get)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: broken:" in captured


def test_floor_unparseable_yaml_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body("rulesets: [this is not: valid: yaml"))

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr()
    assert "repo-floor: broken:" in captured.err
    assert "repo-floor: shortfall:" not in captured.err


def test_rulesets_list_fetch_failure_is_broken(monkeypatch, capsys):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_ONE_CONTEXT_FLOOR))
    fake.list_pages = [(404, _headers(), "")]

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr().err
    assert "repo-floor: broken:" in captured
    assert "repo-floor: shortfall:" not in captured


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


# ---------------------------------------------------------------------------------------------
# Floor-shape faults (H4): broken, loaded with yaml.safe_load
# ---------------------------------------------------------------------------------------------

_SHAPE_FAULTS = {
    "not_a_mapping": "- just\n- a\n- list\n",
    "no_rulesets_key": "other_key: 1\n",
    "rulesets_empty": "rulesets: []\n",
    "rulesets_not_a_list": "rulesets: {}\n",
    "entry_without_name": "rulesets:\n  - target: branch\n    enforcement: active\n    rules: []\n",
    "rule_without_type": (
        "rulesets:\n  - name: x\n    target: branch\n    enforcement: active\n"
        "    rules:\n      - parameters: {}\n"
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
def test_floor_shape_fault_is_broken(monkeypatch, capsys, fault):
    fake = FakeAPI()
    fake.floor = (200, _headers(), _contents_body(_SHAPE_FAULTS[fault]))

    code = _expect_fail(monkeypatch, fake)

    assert code == 1
    captured = capsys.readouterr()
    assert "repo-floor: broken:" in captured.err
    assert "repo-floor: shortfall:" not in captured.err
    assert "repo-floor: repository meets the floor" not in captured.out


# ---------------------------------------------------------------------------------------------
# Floor ref selection (R8/H12): WisewareOrg/.github's own pull_request reads the PR head, every
# other case reads "main" -- the exception is keyed on the repository, not generically on the
# event name. Each case fails the floor fetch itself (a deliberate 404) after it is made, since
# only the requested URL matters here, not a full comparison.
# ---------------------------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------------------------
# api_get itself: its own branches, patching urllib.request.urlopen (not api_get) -- check-branch's
# bottom-section pattern.
# ---------------------------------------------------------------------------------------------


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


def test_api_get_never_prints_the_token(monkeypatch, capsys):
    def fake_urlopen(_request):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit):
        rf.api_get("https://api.github.com/repos/x/y", TOKEN)

    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err


# ---------------------------------------------------------------------------------------------
# __main__ guard -- coverage for `sys.exit(main())`, without a pragma (check-branch's pattern)
# ---------------------------------------------------------------------------------------------


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
