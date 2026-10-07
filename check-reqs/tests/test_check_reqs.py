"""Specifies check_reqs's runner: the fixed stage order and stop (check_unreviewed,
check_suspect_links, doorstop, check_method_consistency, check_text_citations, check_headers,
report_proposed), `--root` resolution, and the req_sha_item_validator hook -- seeded from every row
of WiseKiosk's scripts/cases/the-requirements-tree-checks.md and scripts/cases/report-proposed-py.md
(check-reqs/README.md).

Each case builds a fresh minimal tree (`minimal_tree.build`) inside a real, isolated git repository
and runs the real console script against it as a subprocess (docs/TESTING.md "Real dependencies
where possible"). Every seed is read back to confirm it landed before the check runs.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest
import yaml

import minimal_tree

SCRIPT = Path(sys.executable).with_name("check-reqs")

STAGES = (
    "check_unreviewed",
    "check_suspect_links",
    "doorstop",
    "check_method_consistency",
    "check_text_citations",
    "check_headers",
    "report_proposed",
)

# The brief moves every pointer at one of these onto check-reqs/README.md instead; no case may
# reintroduce one.
NO_WISEKIOSK_DOC = ("docs/requirements/README.md", "ADR", "check-arch-trace", "check-citations")

SYS1 = "docs/requirements/sys/SYS001.yml"
SRS1 = "docs/requirements/srs/SRS001.yml"
TST1 = "docs/requirements/tst/TST001.yml"

# Shuts out the machine's own git configuration (docs/TESTING.md "Real dependencies where
# possible"), as check-eol's tests do.
_ISOLATION = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
_IDENTITY = {
    "GIT_AUTHOR_NAME": "check-reqs tests",
    "GIT_AUTHOR_EMAIL": "check-reqs-tests@wise-ci.invalid",
    "GIT_COMMITTER_NAME": "check-reqs tests",
    "GIT_COMMITTER_EMAIL": "check-reqs-tests@wise-ci.invalid",
}


def _env(**overrides: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_ISOLATION)
    env.update(_IDENTITY)
    env.update(overrides)
    return env


def _init_repo(path: Path) -> Path:
    result = subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)], env=_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return path


def _repo(tmp_path: Path) -> Path:
    """A fresh, isolated git repository holding the minimal tree."""
    repo = _init_repo(tmp_path / "repo")
    minimal_tree.build(repo)
    return repo


def _run_check(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT), *args], cwd=repo, env=_env(), capture_output=True, text=True)


def _run_review(repo: Path, uid: str) -> None:
    result = subprocess.run(
        [str(minimal_tree.DOORSTOP), "review", uid], cwd=repo, env=_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def _run_clear(repo: Path, uid: str) -> None:
    result = subprocess.run(
        [str(minimal_tree.DOORSTOP), "clear", uid], cwd=repo, env=_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _dump(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _set_fields(path: Path, **fields) -> None:
    data = _load(path)
    data.update(fields)
    _dump(path, data)
    landed = _load(path)
    for key, value in fields.items():
        assert landed[key] == value


def _delete_key(path: Path, key: str) -> None:
    data = _load(path)
    del data[key]
    _dump(path, data)
    assert key not in _load(path)


def _reviewed_edit(repo: Path, path: Path, uid: str, *, clears: tuple = (), **fields) -> None:
    """Mutates a field the review fingerprint covers (`text`, `rationale`, `verification-method`,
    `verification-justification`), then re-reviews `uid` and clears every child in `clears` so the
    tree stays valid up to the stage under test -- Doorstop stamps `reviewed:` for any such field it
    has no stamp for, and an unstamped change is what the `doorstop` stage itself catches first."""
    before = _load(path)["reviewed"]
    _set_fields(path, **fields)
    _run_review(repo, uid)
    for child in clears:
        _run_clear(repo, child)
    assert _load(path)["reviewed"] != before


def _reviewed_delete(repo: Path, path: Path, uid: str, key: str, *, clears: tuple = ()) -> None:
    before = _load(path)["reviewed"]
    _delete_key(path, key)
    _run_review(repo, uid)
    for child in clears:
        _run_clear(repo, child)
    assert _load(path)["reviewed"] != before


def _stage_header(stage: str) -> str:
    return f"check-reqs: {stage}"


def _no_traceback(result: subprocess.CompletedProcess) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def _no_wisekiosk_reference(combined: str) -> None:
    for text in NO_WISEKIOSK_DOC:
        assert text not in combined


@dataclass(frozen=True)
class _Case:
    id: str
    build: Callable[[Path], Path]
    check: Callable[[subprocess.CompletedProcess], None]
    args: tuple = field(default=("--root", "docs/requirements"))


def _seed(editor: Callable[[Path], None]) -> Callable[[Path], Path]:
    """Builds the minimal tree, then applies `editor(repo)` to it -- every editor confirms its own
    seed landed, via `_set_fields`/`_delete_key` or its own read-back."""

    def build(tmp_path: Path) -> Path:
        repo = _repo(tmp_path)
        editor(repo)
        return repo

    return build


def _must_fail_at(stage: str, *, has: str | tuple = ()) -> Callable:
    idx = STAGES.index(stage)
    needles = (has,) if isinstance(has, str) else has

    def check(result: subprocess.CompletedProcess) -> None:
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        for s in STAGES[: idx + 1]:
            assert _stage_header(s) in combined
        for s in STAGES[idx + 1 :]:
            assert _stage_header(s) not in combined
        for needle in needles:
            assert needle in combined
        _no_traceback(result)
        _no_wisekiosk_reference(combined)

    return check


def _must_pass(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    for s in STAGES:
        assert _stage_header(s) in combined
    _no_traceback(result)
    _no_wisekiosk_reference(combined)


def _raw_unreviewed_item(document: Path, stem: str, header: str, text: str, suffix: str = ".yml") -> Path:
    """Writes an item file directly, bypassing the `doorstop` CLI, carrying no review fingerprint --
    safe only for check_unreviewed rows, whose stage runs before Doorstop itself ever reads the
    tree."""
    path = document / f"{stem}{suffix}"
    _dump(
        path,
        {
            "active": True, "derived": False, "header": header, "level": 1.0, "links": [],
            "normative": True, "rationale": "", "ref": "", "reviewed": None, "status": "accepted",
            "text": text, "verification-justification": "irrelevant to this stage",
            "verification-method": "test",
        },
    )
    assert _load(path)["reviewed"] is None
    return path


# -- check_unreviewed: multi-step seeds (simple one-field seeds are inlined in CASES below) -------


def _cu_silo_renamed(repo: Path) -> None:
    (repo / "docs/requirements/sys").rename(repo / "docs/requirements/system")
    assert not (repo / "docs/requirements/sys").exists()
    assert (repo / "docs/requirements/system/.doorstop.yml").exists()


def _cu_nested_item_unreviewed(repo: Path) -> None:
    document = minimal_tree.add_document(repo, "docs/requirements/sys/nested", "NST", parent="SYS")
    _raw_unreviewed_item(document, "NST001", "Nested, unreviewed", "An unreviewed nested item.")


def _cu_silo_removed(repo: Path) -> None:
    shutil.rmtree(repo / "docs/requirements/sys")
    assert not (repo / "docs/requirements/sys").exists()


def _cu_all_silos_removed(repo: Path) -> None:
    for silo in ("sys", "srs", "tst"):
        shutil.rmtree(repo / "docs/requirements" / silo)
    assert not any((repo / "docs/requirements" / s).exists() for s in ("sys", "srs", "tst"))


def _cu_silo_emptied(repo: Path) -> None:
    (repo / SYS1).unlink()
    assert not (repo / SYS1).exists()
    assert (repo / "docs/requirements/sys/.doorstop.yml").exists()


def _cu_nested_no_items(repo: Path) -> None:
    minimal_tree.add_document(repo, "docs/requirements/sys/nested", "NST", parent="SYS")
    assert [p.name for p in (repo / "docs/requirements/sys/nested").glob("*.yml")] == [".doorstop.yml"]


def _cu_two_nested_share_dirname(repo: Path) -> None:
    full = minimal_tree.add_document(repo, "docs/requirements/sys/extra", "SX1", parent="SYS")
    minimal_tree.add_reviewed_item(
        repo, "docs/requirements/sys/extra", "SX1",
        header="Reviewed sibling of an empty namesake",
        text="Reviewed, so this document itself is not the failure.",
        verification_justification="Exists only to be reviewed.",
    )
    empty = minimal_tree.add_document(repo, "docs/requirements/srs/extra", "SX2", parent="SRS")
    assert full.name == empty.name == "extra"
    assert [p.name for p in empty.glob("*.yml")] == [".doorstop.yml"]


def _cu_fourth_tier_and_nested_pass(repo: Path) -> None:
    # Doorstop refuses a second root document (verified: "multiple root documents"), so the
    # fourth tier extends the hierarchy one level past TST rather than standing beside SYS.
    minimal_tree.add_document(repo, "docs/requirements/qa", "QA", parent="TST")
    minimal_tree.add_reviewed_item(
        repo, "docs/requirements/qa", "QA",
        header="Extra fourth-tier item",
        text="An item belonging to a document outside the three required tiers.",
        verification_justification="Proves the extra tier is accepted.",
        parent_uid="TST001",
    )
    minimal_tree.add_document(repo, "docs/requirements/sys/nested", "NST", parent="SYS")
    minimal_tree.add_reviewed_item(
        repo, "docs/requirements/sys/nested", "NST",
        header="Extra nested item",
        text="An item belonging to a document nested below an existing tier.",
        verification_justification="Proves a nested document is accepted.",
        parent_uid="SYS001",
    )


def _cu_venv_doorstop_yml_pass(repo: Path) -> None:
    venv_dir = repo / "docs/requirements/.venv"
    venv_dir.mkdir()
    _dump(venv_dir / ".doorstop.yml", {"settings": {"prefix": "TOOL", "digits": 3, "sep": ""}})
    assert (venv_dir / ".doorstop.yml").exists()


# -- check_suspect_links ---------------------------------------------------------------------------


def _csl_parent_mutated_stale(repo: Path) -> None:
    # TST001 is deactivated first and never re-cleared: its stale link to SRS001 is the one thing
    # under test. SRS001 is re-reviewed so the only remaining defect is that staleness, not an
    # unrelated "SRS001 unreviewed changes" the doorstop stage would otherwise report first.
    _set_fields(repo / TST1, active=False)
    _reviewed_edit(repo, repo / SRS1, "SRS001", text="The software shall do a mutated thing.\n")


def _csl_inactive_dangling_parent(repo: Path) -> None:
    _set_fields(repo / TST1, active=False)
    stamp = _load(repo / TST1)["links"][0]["SRS001"]
    _set_fields(repo / TST1, links=[{"SRS999": stamp}])


# -- doorstop (the --error-all --no-reformat subprocess) -------------------------------------------


def _doorstop_active_orphan_link(repo: Path) -> None:
    stamp = _load(repo / SRS1)["links"][0]["SYS001"]
    _set_fields(repo / SRS1, links=[{"SYS999": stamp}])


# -- check_method_consistency: the one multi-step seed ---------------------------------------------


def _mc_normative_false_pass(repo: Path) -> None:
    minimal_tree.add_reviewed_item(
        repo, "docs/requirements/srs", "SRS",
        header="Extra non-normative note", text="An orientation note, not an obligation.",
        verification_method="", verification_justification="",
    )
    _set_fields(repo / "docs/requirements/srs/SRS002.yml", normative=False)
    _run_review(repo, "SRS002")


CASES: list[_Case] = [
    # check_unreviewed
    _Case("cu-reviewed-deleted", _seed(lambda r: _delete_key(r / SYS1, "reviewed")),
          _must_fail_at("check_unreviewed", has=("carry no review fingerprint", "SYS001"))),
    _Case("cu-reviewed-true-bool", _seed(lambda r: _set_fields(r / SYS1, reviewed=True)),
          _must_fail_at("check_unreviewed", has="carry no review fingerprint")),
    _Case("cu-reviewed-empty-string", _seed(lambda r: _set_fields(r / SYS1, reviewed="")),
          _must_fail_at("check_unreviewed", has="carry no review fingerprint")),
    _Case("cu-yaml-suffix-unreviewed",
          _seed(lambda r: _raw_unreviewed_item(r / "docs/requirements/sys", "SYS002", "Extra", "Extra item.", ".yaml")),
          _must_fail_at("check_unreviewed", has=("carry no review fingerprint", "SYS002"))),
    _Case("cu-link-stamp-copied-by-hand", _seed(lambda r: _delete_key(r / SRS1, "reviewed")),
          _must_fail_at("check_unreviewed", has=("carry no review fingerprint", "SRS001"))),
    _Case("cu-silo-removed", _seed(_cu_silo_removed),
          _must_fail_at("check_unreviewed", has="holds no document — missing, renamed, or deleted.")),
    _Case("cu-silo-renamed", _seed(_cu_silo_renamed),
          _must_fail_at("check_unreviewed", has="holds no document — missing, renamed, or deleted.")),
    _Case("cu-nested-item-unreviewed", _seed(_cu_nested_item_unreviewed),
          _must_fail_at("check_unreviewed", has=("carry no review fingerprint", "NST001"))),
    _Case("cu-all-silos-removed", _seed(_cu_all_silos_removed),
          _must_fail_at("check_unreviewed", has="holds no document — missing, renamed, or deleted.")),
    _Case("cu-silo-emptied", _seed(_cu_silo_emptied),
          _must_fail_at("check_unreviewed", has="yielded no item — this check read none of it.")),
    _Case("cu-nested-no-items", _seed(_cu_nested_no_items),
          _must_fail_at("check_unreviewed", has="yielded no item — this check read none of it.")),
    _Case("cu-two-nested-share-dirname-one-empty", _seed(_cu_two_nested_share_dirname),
          _must_fail_at("check_unreviewed", has="yielded no item — this check read none of it.")),
    _Case("cu-fourth-tier-and-nested-pass", _seed(_cu_fourth_tier_and_nested_pass), _must_pass),
    _Case("cu-venv-doorstop-yml-pass", _seed(_cu_venv_doorstop_yml_pass), _must_pass),

    # check_suspect_links
    _Case("csl-parent-mutated-stale", _seed(_csl_parent_mutated_stale),
          _must_fail_at("check_suspect_links", has=("are suspect", "TST001", "SRS001"))),
    _Case("csl-inactive-dangling-parent", _seed(_csl_inactive_dangling_parent),
          _must_fail_at("check_suspect_links", has=("name a parent the tree does not hold", "SRS999"))),

    # doorstop
    _Case("doorstop-active-orphan-link", _seed(_doorstop_active_orphan_link),
          _must_fail_at("doorstop", has="no item with UID: SYS999")),

    # check_method_consistency
    _Case("mc-blanked-justification",
          _seed(lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), **{"verification-justification": ""})),
          _must_fail_at("check_method_consistency", has=("carry no verification-justification", "SYS001"))),
    _Case("mc-parent-overstates",
          _seed(lambda r: _reviewed_edit(r, r / TST1, "TST001", **{"verification-method": "inspection"})),
          _must_fail_at("check_method_consistency", has=("above its least-decidable child", "SRS001"))),
    _Case("mc-parent-understates-no-justification",
          _seed(lambda r: _reviewed_edit(r, r / SRS1, "SRS001", clears=("TST001",), **{"verification-method": "inspection", "verification-justification": ""})),
          _must_fail_at("check_method_consistency", has=("below every child with no verification-justification", "SRS001"))),
    _Case("mc-capitalised-method",
          _seed(lambda r: _reviewed_edit(r, r / TST1, "TST001", **{"verification-method": "Test"})),
          _must_fail_at("check_method_consistency", has=("carry an unrecognised verification-method", "'Test' is not one of"))),
    _Case("mc-typo-method",
          _seed(lambda r: _reviewed_edit(r, r / TST1, "TST001", **{"verification-method": "tset"})),
          _must_fail_at("check_method_consistency", has=("carry an unrecognised verification-method", "'tset' is not one of"))),
    _Case("mc-method-key-deleted", _seed(lambda r: _reviewed_delete(r, r / TST1, "TST001", "verification-method")),
          _must_fail_at("check_method_consistency", has=("carry an unrecognised verification-method", "TST001"))),
    _Case("mc-normative-false-pass", _seed(_mc_normative_false_pass), _must_pass),

    # check_text_citations
    _Case("tc-identifier-in-text",
          _seed(lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), text="The system shall match SRS001 exactly.\n")),
          _must_fail_at("check_text_citations", has=("cite another item in `text`", "SYS001 -> SRS001"))),
    _Case("tc-lowercase-identifier-in-text",
          _seed(lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), text="The system shall match srs001 exactly.\n")),
          _must_fail_at("check_text_citations", has="cite another item in `text`")),
    _Case("tc-identifier-in-rationale-pass",
          _seed(lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), rationale="Decomposed by SRS001, which is fine to name here.\n")),
          _must_pass),

    # check_headers (header is outside the review fingerprint -- no re-review needed)
    _Case("ch-emptied-header", _seed(lambda r: _set_fields(r / SYS1, header="")),
          _must_fail_at("check_headers", has=("SYS001", "has no header"))),
    _Case("ch-slash-in-header", _seed(lambda r: _set_fields(r / SYS1, header="Sample system/need")),
          _must_fail_at("check_headers", has=("outside the permitted set", "'/'"))),
    _Case("ch-en-dash-in-header", _seed(lambda r: _set_fields(r / SYS1, header="Sample system–need")),
          _must_fail_at("check_headers", has="outside the permitted set")),
    _Case("ch-nbsp-in-header", _seed(lambda r: _set_fields(r / SYS1, header=" Sample system need")),
          _must_fail_at("check_headers", has="outside the permitted set")),
    _Case("ch-folded-header-pass", _seed(lambda r: _set_fields(r / SYS1, header="Sample system\nneed, folded")),
          _must_pass),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: _Case, tmp_path: Path) -> None:
    repo = case.build(tmp_path)
    result = _run_check(repo, *case.args)
    case.check(result)


# -- report_proposed: always exits 0; every row is about the report's own lines -------------------


@pytest.mark.parametrize(
    ("seed", "must_contain"),
    [
        pytest.param(
            None,
            ("SYS: 0 of 1 item(s) proposed", "SRS: 0 of 1 item(s) proposed", "TST: 0 of 1 item(s) proposed"),
            id="baseline-every-tier-accepted-zero-line-does-not-disappear",
        ),
        pytest.param(
            lambda r: [_set_fields(r / p, status="proposed") for p in (SYS1, SRS1, TST1)],
            ("SYS: 1 of 1 item(s) proposed: SYS001", "SRS: 1 of 1 item(s) proposed: SRS001", "TST: 1 of 1 item(s) proposed: TST001"),
            id="proposed-in-every-tier",
        ),
        pytest.param(
            lambda r: _set_fields(r / SYS1, status="acepted"),
            ("carry a status outside proposed | accepted, counted in neither", "SYS001 (acepted)"),
            id="misspelled-status",
        ),
        pytest.param(
            lambda r: _delete_key(r / SYS1, "status"),
            ("SYS: 1 of 1 item(s) proposed: SYS001",),
            id="status-key-deleted-counted-at-document-default",
        ),
    ],
)
def test_report_proposed_lines(tmp_path: Path, seed, must_contain: tuple) -> None:
    repo = _repo(tmp_path)
    if seed is not None:
        seed(repo)

    result = _run_check(repo, "--root", "docs/requirements")

    _must_pass(result)
    for text in must_contain:
        assert text in result.stdout


# -- --root: resolution against the working directory, never the package's own location -----------


def test_missing_root_fails_at_check_unreviewed_with_the_resolved_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    assert not (repo / "docs/requirements").exists()

    result = _run_check(repo, "--root", "docs/requirements")

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert _stage_header("check_unreviewed") in combined
    for stage in STAGES[1:]:
        assert _stage_header(stage) not in combined
    resolved = repo / "docs/requirements"
    for silo in ("sys", "srs", "tst"):
        assert f"{resolved / silo}/ holds no document — missing, renamed, or deleted." in combined
    _no_traceback(result)


def test_absolute_root_is_accepted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _must_pass(_run_check(repo, "--root", str(repo / "docs/requirements")))


def test_default_root_is_docs_requirements(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _must_pass(_run_check(repo))


# -- req_sha_item_validator: the TST extension hook --------------------------------------------


def test_req_sha_item_validator_fails_when_referenced_file_changed_since_review(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "verified-file.txt").write_text("verified behaviour\n")
    _set_fields(repo / TST1, references=[{"path": "verified-file.txt", "type": "file"}])
    _run_review(repo, "TST001")
    assert _load(repo / TST1)["references"][0].get("sha")
    (repo / "verified-file.txt").write_text("a different line\n")

    result = _run_check(repo, "--root", "docs/requirements")

    _must_fail_at("doorstop", has="referenced file changed since review: verified-file.txt")(result)


def test_req_sha_item_validator_no_sha_recorded_backstopped_by_doorstop_itself(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "untracked-reference.txt").write_text("not yet reviewed against\n")
    _set_fields(repo / TST1, references=[{"path": "untracked-reference.txt", "type": "file"}])
    assert _load(repo / TST1)["references"][0].get("sha") is None

    result = _run_check(repo, "--root", "docs/requirements")

    assert "referenced file changed since review" not in (result.stdout + result.stderr)
    _must_fail_at("doorstop", has="unreviewed changes")(result)


# -- Order: check_unreviewed runs before Doorstop ever validates, so its own stop -- and a clean
# pass -- leave every item file byte-identical.
# -------------------------------------------------------------------------------------------------


def _item_bytes(repo: Path) -> dict[str, bytes]:
    return {relpath: (repo / relpath).read_bytes() for relpath in (SYS1, SRS1, TST1)}


def test_failing_at_check_unreviewed_leaves_the_tree_byte_identical(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _delete_key(repo / SYS1, "reviewed")
    before = _item_bytes(repo)

    result = _run_check(repo, "--root", "docs/requirements")

    _must_fail_at("check_unreviewed")(result)
    assert _item_bytes(repo) == before


def test_passing_tree_is_byte_identical_after_the_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _item_bytes(repo)

    result = _run_check(repo, "--root", "docs/requirements")

    _must_pass(result)
    assert _item_bytes(repo) == before


# -- check_suspect_links only examines inactive items: an active parent's own suspect link is
# Doorstop's own problem one stage later, not this stage's.
# -------------------------------------------------------------------------------------------------


def test_suspect_links_passes_for_an_active_parent_mutation_which_doorstop_then_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _set_fields(repo / SYS1, text="The system shall do a mutated thing.\n")

    result = _run_check(repo, "--root", "docs/requirements")

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert _stage_header("check_suspect_links") in combined
    assert "Every inactive item's links resolve and match the parents they were reviewed against." in combined
    assert _stage_header("doorstop") in combined
    for stage in STAGES[3:]:
        assert _stage_header(stage) not in combined
    _no_traceback(result)
    _no_wisekiosk_reference(combined)
