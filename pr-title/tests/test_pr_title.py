"""Specifies pr-title/pr-title.py: enforces WisewareOrg/.github PROCESS.md PROC-009 (the pull
request title, which becomes the commit that reaches the default branch under squash-merge, must
be a Conventional Commit), by handing the title to the real commitlint on stdin.

Mirrors check-branch/check_branch/__init__.py's shape exactly:
`api_request(url, token, payload=None)`; a `fail(message)` helper that prints `pr-title: <message>`
to stderr and calls `sys.exit(1)`; `main()` returning `None` on success, with
`if __name__ == "__main__": sys.exit(main())`; the API base hardcoded as `https://api.github.com`.
It reads `HEAD_REF`, `TITLE`, `PR_NUMBER`, `GITHUB_TOKEN` and the runner's own `GITHUB_REPOSITORY`.

Test mechanism, copied from check-branch/tests/test_check_branch.py:
- load the script in-process with `importlib` (`:51-62`);
- fake the API with a `FakeAPI` matched by URL shape and installed with
  `monkeypatch.setattr(..., "api_request", ...)` (`:80-110`, `:159`);
- test the HTTP branches of `api_request` through a patched `urlopen` (`:746-811`);
- run the `__main__` guard through `runpy` (`:825`).

The title-case tests run the real commitlint through the script (docs/TESTING.md "Real
dependencies where possible"), from a temporary, non-git cwd (an autouse fixture below) -- this
suite's own run against each title is the proof. A must-fail case asserts the commitlint exit code
is passed through non-zero (`sys.exit(<code>)`, not hardcoded) and that this suite's one pinned
rule id appears in commitlint's own stdout (`capfd`, which catches a subprocess's inherited file
descriptors the way `capsys` does not) -- a second rule id commitlint also reports for the same
title is not asserted away, since this suite pins one id per title, not an exhaustive set.

Dropped: a dedicated test that a broken `.commitlintrc-pr-title.json` fails differently from a bad
title (it fails the same way, exit 1 either way, and this suite's own rule-id assertions already
guard it: a stack trace on stderr carries no rule id on stdout, so a must-fail case would fail for
the wrong reason instead of passing). The API-error case asserts only a non-zero exit, not
exit-code-1 or message text, since this path going through `fail()` is unstated, unlike the two
cases below that give exact message text.
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

SCRIPT = Path(__file__).resolve().parents[1] / "pr-title.py"

REPO = "WisewareOrg/wise-ci"
TOKEN = "test-token-abc123"  # noqa: S105 -- a fixture value, never a real credential


def _load_module():
    spec = importlib.util.spec_from_file_location("pr_title", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A fresh import, once: the script has no module-level side effects (main() reads env at call
# time, mirroring check-branch), so every test below shares this one module object and
# monkeypatches its `api_request` name and the process environment per case.
pt = _load_module()


@pytest.fixture(autouse=True)
def _non_git_cwd(tmp_path, monkeypatch):
    """Every case runs from a temporary directory that is not a git repository, per
    docs/TESTING.md's "a test gives the same result on any machine": the machine's own git
    configuration is shut out for every case, not only the title-matrix ones."""
    monkeypatch.chdir(tmp_path)


def _env(monkeypatch, *, title=None, pr_number=None, token=TOKEN, repository=REPO, head_ref=None):
    for name, value in (
        ("HEAD_REF", head_ref),
        ("TITLE", title),
        ("PR_NUMBER", pr_number),
        ("GITHUB_TOKEN", token),
        ("GITHUB_REPOSITORY", repository),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


class FakeAPI:
    """Stands in for pr-title.py's `api_request`. Dispatches on the URL's own shape -- a
    `.../pulls/<n>` REST endpoint -- rather than a literal URL, so this fake does not also pin how
    the script builds that URL out of GITHUB_REPOSITORY; that construction is an implementation
    choice, not a boundary this suite pins. A call this fixture was not given a canned reply for
    raises, so a main() that calls the API in a way a test did not expect fails loudly rather than
    silently returning something plausible."""

    def __init__(self):
        self.pull = None
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, url, token, payload=None):
        self.calls.append((url, token, payload))
        if re.search(r"/pulls/\d+$", url):
            if self.pull is None:
                raise AssertionError(f"unexpected pull lookup: {url}")
            return self.pull
        raise AssertionError(f"unexpected API call: {url}")


def _no_api_call(*_args, **_kwargs):
    raise AssertionError("api_request must not be called")


def _pull(*, title):
    return (200, {"title": title})


def _run(monkeypatch, fake, **env_kwargs):
    monkeypatch.setattr(pt, "api_request", fake)
    _env(monkeypatch, **env_kwargs)


def _expect_fail(monkeypatch, fake, **env_kwargs):
    _run(monkeypatch, fake, **env_kwargs)
    with pytest.raises(SystemExit) as exc_info:
        pt.main()
    return exc_info.value.code


def _expect_pass(monkeypatch, fake, **env_kwargs):
    _run(monkeypatch, fake, **env_kwargs)
    pt.main()  # must return, not raise


# ---------------------------------------------------------------------------------------------
# Title cases: the real commitlint, through the script, from a non-git tmp cwd (autouse fixture).
# Seeded from PROC-009 and the shipped commitlint configs. The list is a seed, not exhaustive --
# further cases are added only if they derive from PROC-009 or the shipped configs; anything else
# is escalated.
# ---------------------------------------------------------------------------------------------

MUST_PASS_TITLES = [
    "feat: add a thing",
    "fix(scope): repair it",
    "chore(deps): update x",
    "feat(deps-dev): bump x",
    "feat!: breaking change",
    "fix: handle API errors",
    "feat: " + "x" * 94,  # a 100-character header
]


@pytest.mark.parametrize("title", MUST_PASS_TITLES)
def test_title_passes_commitlint(monkeypatch, title):
    _expect_pass(monkeypatch, _no_api_call, title=title)


MUST_FAIL_TITLES = [
    ("nope", "type-empty"),
    ("Feat: x", "type-case"),
    ("foo: x", "type-enum"),
    ("feat(Scope): x", "scope-case"),
    ("feat(Backend): x", "scope-case"),
    ("feat: X Is Start Case", "subject-case"),
    ("feat: Add retry to the uploader", "subject-case"),
    ("feat: x.", "subject-full-stop"),
    ("feat: " + "x" * 95, "header-max-length"),  # 101 characters
    ("feat:no space", "subject-empty"),
    ("fixup! feat: x", "type-empty"),
    ("squash! feat: x", "type-empty"),
    ("Merge branch 'main' into x", "type-empty"),
    ("Merge pull request #1 from o/b", "type-empty"),
    ('Revert "feat: x"', "type-empty"),
]


@pytest.mark.parametrize(("title", "rule_id"), MUST_FAIL_TITLES)
def test_title_fails_commitlint_with_its_rule_id(monkeypatch, capfd, title, rule_id):
    code = _expect_fail(monkeypatch, _no_api_call, title=title)

    assert code != 0
    captured = capfd.readouterr()
    assert f"[{rule_id}]" in captured.out


def test_trailing_newline_on_the_title_makes_no_difference(monkeypatch):
    """'feat: add a thing' and 'feat: add a thing\\n' both exit 0 through commitlint on stdin."""
    _expect_pass(monkeypatch, _no_api_call, title="feat: add a thing\n")


# ---------------------------------------------------------------------------------------------
# PROC-009's exemption: Dependabot's own branches.
# ---------------------------------------------------------------------------------------------


def test_dependabot_branch_is_exempt_without_reading_the_title(monkeypatch, capsys):
    """The API fixture raises on any call: an exempt branch never fetches its title."""
    _expect_pass(monkeypatch, _no_api_call, head_ref="dependabot/npm_and_yarn/x", pr_number="7")

    assert "exempt" in capsys.readouterr().out


def test_dependabot_branch_is_exempt_even_with_a_failing_title(monkeypatch):
    _expect_pass(monkeypatch, _no_api_call, head_ref="dependabot/npm_and_yarn/x", title="nope")


def test_renovate_branch_is_not_exempt(monkeypatch, capfd):
    """PROC-009 exempts only `dependabot/*`: Renovate's titles are still checked."""
    code = _expect_fail(monkeypatch, _no_api_call, head_ref="renovate/x", title="nope")

    assert code != 0
    assert "[type-empty]" in capfd.readouterr().out


# ---------------------------------------------------------------------------------------------
# Selection: the title input vs. the API vs. no PR context, and the empty-title guard.
# ---------------------------------------------------------------------------------------------


def test_title_input_wins_over_the_api(monkeypatch):
    """A PR_NUMBER is also present, with the API fixture set to raise on any call -- if main()
    reached for the API instead of the given title, this test would fail loudly rather than
    silently passing."""
    _expect_pass(monkeypatch, _no_api_call, title="feat: add a thing", pr_number="7")


def test_pr_number_fetches_the_title_from_the_api_and_passes(monkeypatch):
    """A PR_NUMBER makes the script fetch repos/{repo}/pulls/{n}, read .title, and use that --
    proven here with a title that then passes commitlint."""
    fake = FakeAPI()
    fake.pull = _pull(title="feat: add a thing")

    _expect_pass(monkeypatch, fake, pr_number="7")


def test_pr_number_fetches_the_title_from_the_api_and_fails(monkeypatch, capfd):
    """The same fetch path, with a title the API returns that commitlint rejects -- proves the
    fetched title is the one actually handed to commitlint, not only that the fetch happens."""
    fake = FakeAPI()
    fake.pull = _pull(title="nope")

    code = _expect_fail(monkeypatch, fake, pr_number="7")

    assert code != 0
    assert "[type-empty]" in capfd.readouterr().out


def test_no_pr_number_and_no_title_fails_closed(monkeypatch, capsys):
    code = _expect_fail(monkeypatch, _no_api_call, title=None, pr_number=None)

    assert code == 1
    assert capsys.readouterr().err.strip() == (
        "pr-title: this event carries no pull request; run pr-title on pull_request"
    )


def test_whitespace_only_title_input_fails_without_calling_the_api(monkeypatch, capsys):
    """A whitespace-only TITLE is non-empty as a string, so the title-input-wins-over-the-API
    selection applies directly -- the API fixture raises on any call, proving the empty-title
    guard is checked after selection, not by falling through to the API."""
    code = _expect_fail(monkeypatch, _no_api_call, title="   ", pr_number="7")

    assert code == 1
    assert capsys.readouterr().err.strip() == "pr-title: the pull request title is empty"


def test_empty_title_from_the_api_fails(monkeypatch, capsys):
    fake = FakeAPI()
    fake.pull = _pull(title="")

    code = _expect_fail(monkeypatch, fake, pr_number="7")

    assert code == 1
    assert capsys.readouterr().err.strip() == "pr-title: the pull request title is empty"


def test_whitespace_only_title_from_the_api_fails(monkeypatch, capsys):
    fake = FakeAPI()
    fake.pull = _pull(title="   ")

    code = _expect_fail(monkeypatch, fake, pr_number="7")

    assert code == 1
    assert capsys.readouterr().err.strip() == "pr-title: the pull request title is empty"


def test_api_error_fetching_the_title_fails(monkeypatch):
    """No message text or exit-code value is pinned beyond non-zero, unlike the two cases above
    that give exact message text."""
    fake = FakeAPI()
    fake.pull = (500, None)

    code = _expect_fail(monkeypatch, fake, pr_number="7")

    assert code != 0


# ---------------------------------------------------------------------------------------------
# The environment handed to commitlint's subprocess: no secret from the runner's own process may
# reach it. COMMITLINT_BIN is monkeypatched to a real stub executable (not a mocked
# subprocess.run) that reports the environment it actually received.
# ---------------------------------------------------------------------------------------------


def test_commitlint_runs_with_an_allowlisted_environment(monkeypatch, capfd, tmp_path):
    """No variable set only in the parent process -- GITHUB_TOKEN or anything else -- reaches
    commitlint's subprocess, by name or by value. Checked against parent-only decoys rather than
    the child's full key set: python3/node/bash wrappers (NixOS, asdf) add their own vars once
    exec'd, so asserting the child's keys are exactly an allowlist fails by host, not by defect
    (docs/TESTING.md "a test gives the same result on any machine"). pt.COMMITLINT_ENV_KEYS is
    still read directly, to confirm GITHUB_TOKEN is excluded from it."""
    stub = tmp_path / "commitlint-stub.py"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "for k, v in sorted(os.environ.items()):\n"
        "    print(f'{k}={v}')\n"
    )
    stub.chmod(0o755)
    monkeypatch.setattr(pt, "COMMITLINT_BIN", stub)

    decoys = {
        "PR_TITLE_TEST_DECOY_1": "decoy-one-must-not-reach-commitlint",
        "PR_TITLE_TEST_DECOY_2": "decoy-two-must-not-reach-commitlint",
    }
    for name, value in decoys.items():
        monkeypatch.setenv(name, value)
    secret = "github-token-must-not-reach-commitlint"

    _expect_pass(monkeypatch, _no_api_call, title="feat: add a thing", token=secret)

    received = dict(
        line.split("=", 1) for line in capfd.readouterr().out.splitlines() if "=" in line
    )

    for name, value in {**decoys, "GITHUB_TOKEN": secret}.items():
        assert name not in received
        assert value not in received.values()
    assert "GITHUB_TOKEN" not in pt.COMMITLINT_ENV_KEYS


# ---------------------------------------------------------------------------------------------
# package.json: commitlint lands under "dependencies", not "devDependencies" -- a consumer
# running `npm ci` under NODE_ENV=production or NPM_CONFIG_OMIT=dev must still get it installed.
# ---------------------------------------------------------------------------------------------

COMMITLINT_PACKAGES = ("@commitlint/cli", "@commitlint/config-conventional")


def test_commitlint_packages_are_production_dependencies():
    package = json.loads((SCRIPT.parent / "package.json").read_text())

    for name in COMMITLINT_PACKAGES:
        assert name in package.get("dependencies", {})
        assert name not in package.get("devDependencies", {})


# ---------------------------------------------------------------------------------------------
# api_request itself: its own branches, patching urllib.request.urlopen (not api_request) --
# mirrors check-branch/tests/test_check_branch.py:746-811 exactly, since pr-title.py mirrors
# api_request's signature and behaviour unchanged.
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

    status, body = pt.api_request("https://api.github.com/repos/x/y", "")

    assert (status, body) == (200, {"ok": True})


def test_api_request_http_error_returns_its_status_code(monkeypatch):
    def fake_urlopen(request):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    status, body = pt.api_request("https://api.github.com/repos/x/y", "")

    assert (status, body) == (404, None)


def test_api_request_url_error_fails_cannot_reach(monkeypatch, capsys):
    def fake_urlopen(_request):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit) as exc_info:
        pt.api_request("https://api.github.com/repos/x/y", "")

    assert exc_info.value.code == 1
    assert "cannot reach" in capsys.readouterr().err


def test_api_request_sends_authorization_only_with_a_token(monkeypatch):
    requests_seen = []

    def fake_urlopen(request):
        requests_seen.append(request)
        return _FakeHTTPResponse(200, {})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    pt.api_request("https://api.github.com/repos/x/y", "")
    pt.api_request("https://api.github.com/repos/x/y", TOKEN)

    assert "Authorization" not in requests_seen[0].headers
    assert requests_seen[1].headers.get("Authorization") == f"Bearer {TOKEN}"


def test_api_request_never_prints_the_token(monkeypatch, capsys):
    def fake_urlopen(_request):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit):
        pt.api_request("https://api.github.com/repos/x/y", TOKEN)

    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err


# ---------------------------------------------------------------------------------------------
# __main__ guard -- coverage for `sys.exit(main())`, without a pragma.
# ---------------------------------------------------------------------------------------------


def test_dunder_main_guard_runs_main_and_exits(monkeypatch):
    """Runs the script the way the action does (`python3 pr-title.py`), to cover the
    `if __name__ == "__main__":` line itself. Uses a scenario that fails before any API call or
    commitlint invocation (no TITLE, no PR_NUMBER), needing no `api_request` patch of its own
    module-fresh run."""
    _env(monkeypatch, title=None, pr_number=None)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert exc_info.value.code == 1
