"""Specifies check_reqs's runner: the fixed stage order (check_unreviewed, check_suspect_links,
doorstop, check_method_consistency, check_text_citations, check_headers, check_citations,
report_proposed), every stage run regardless of an earlier failure, `not judged -- <reason>` where
a precondition failed, `--root` resolution, and the req_sha_item_validator hook -- seeded from
every row of WiseKiosk's scripts/cases/the-requirements-tree-checks.md,
scripts/cases/check-citations-py.md (the requirement half only -- the ADR half is check-adrs'), and
scripts/cases/report-proposed-py.md (check-reqs/README.md).

Each case runs the real console script, as a subprocess, against its own copy of the session's one
baseline minimal tree (conftest.py's `repo` fixture; docs/TESTING.md "Real dependencies where
possible"). Every seed is read back to confirm it landed before the check runs.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
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
    "check_citations",
    "report_proposed",
)

# The brief moves every pointer at one of these onto check-reqs/README.md instead; no case may
# reintroduce one.
NO_WISEKIOSK_DOC = ("docs/requirements/README.md", "ADR", "check-arch-trace", "check-citations")

SYS1 = "docs/requirements/sys/SYS001.yml"
SRS1 = "docs/requirements/srs/SRS001.yml"
TST1 = "docs/requirements/tst/TST001.yml"


def _run_check(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT), *args], cwd=repo, env=minimal_tree.env(), capture_output=True, text=True
    )


def _run_review(repo: Path, uid: str) -> None:
    result = subprocess.run(
        [str(minimal_tree.DOORSTOP), "review", uid],
        cwd=repo,
        env=minimal_tree.env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _run_clear(repo: Path, uid: str) -> None:
    result = subprocess.run(
        [str(minimal_tree.DOORSTOP), "clear", uid],
        cwd=repo,
        env=minimal_tree.env(),
        capture_output=True,
        text=True,
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


# The three reasons a precondition leaves a later stage un-run under run-every-stage. Each is
# printed by the dispatcher itself, on stdout, immediately after that stage's own header.
_CHECK_UNREVIEWED_FAILED = "check_unreviewed failed"
_TREE_DID_NOT_LOAD = "the requirements tree did not load"
_NOT_A_GIT_WORKING_COPY = "not a git working copy"


def _not_judged(stage: str, reason: str) -> str:
    return f"{_stage_header(stage)}\nnot judged — {reason}"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], env=minimal_tree.env(), capture_output=True, text=True
    )


def _no_traceback(result: subprocess.CompletedProcess) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def _no_wisekiosk_reference(combined: str) -> None:
    for text in NO_WISEKIOSK_DOC:
        assert text not in combined


@dataclass(frozen=True)
class _Case:
    id: str
    seed: Callable[[Path], None]
    check: Callable[[subprocess.CompletedProcess], None]


# Every stage but `doorstop` prints exactly one of these on an outright pass, with no variable
# text before the point checked here -- its absence is what ties a failure to the named stage
# rather than to stray matching text elsewhere in the output. `doorstop` carries the same progress
# chatter on its own stdout whether it passes or fails, so it is tied by the `ERROR:` prefix its
# own failures carry instead; `report_proposed` never fails, so neither is needed for it.
_PASS_MARKER = {
    "check_unreviewed": "Every item and every link carries a review fingerprint.",
    "check_suspect_links": "Every inactive item's links resolve and match the parents they were reviewed against.",
    "check_method_consistency": "carry a verification-justification; methods are consistent across",
    "check_text_citations": "No item's `text` cites another item.",
    "check_headers": "Every header is non-empty, within the permitted set, and prefix-free (",
    "check_citations": "Every citation resolves, and every requirement citation carries its item's header.",
}


def _must_fail_at(stage: str, *, has: str | tuple = ()) -> Callable:
    assert stage in STAGES
    needles = (has,) if isinstance(has, str) else has

    def check(result: subprocess.CompletedProcess) -> None:
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        # Every stage's header prints regardless of an earlier failure (run-every-stage): a later
        # stage is either judged -- and prints its own pass or fail content -- or not judged; never
        # silently absent.
        for s in STAGES:
            assert _stage_header(s) in result.stdout
        # Ties the failure to the named stage specifically: it did not pass, and it was not gated
        # as not-judged either -- the two ways a needle could otherwise match while the real fault
        # sat somewhere else.
        if stage == "doorstop":
            assert "ERROR:" in result.stderr
        else:
            assert _PASS_MARKER[stage] not in result.stdout
        for reason in (_CHECK_UNREVIEWED_FAILED, _TREE_DID_NOT_LOAD, _NOT_A_GIT_WORKING_COPY):
            assert _not_judged(stage, reason) not in result.stdout
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


def _check_unstamped_link_outside_root_passes_stage_two_then_fails_at_doorstop(
    result: subprocess.CompletedProcess,
) -> None:
    """Stage 1 never walks outside `root`, so it passes; stage 2 walks from the working directory,
    finds the unstamped link, and silently skips it (its own pass line prints); stage 3 then fails
    on the same outside-root document, whose only item being inactive leaves it with none. Nothing
    here is gated -- check_unreviewed passed, and root's own tree still loads -- so every later
    stage still runs."""
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert _stage_header("check_unreviewed") in combined
    assert _stage_header("check_suspect_links") in combined
    assert "Every inactive item's links resolve and match the parents they were reviewed against." in combined
    assert _stage_header("doorstop") in combined
    for s in STAGES[3:]:
        assert _stage_header(s) in result.stdout
    assert "not judged" not in combined
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


def _cu_silo_removed_leaves_doorstop_stages_not_judged(result: subprocess.CompletedProcess) -> None:
    """check_unreviewed fails on the missing silo. The dispatcher gates doorstop on that failure,
    and check_suspect_links/check_text_citations/check_headers/check_citations on the tree failing
    to load, rather than letting any of them reach doorstop.build() over a tree with an unplaced
    document."""
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "holds no document — missing, renamed, or deleted." in combined
    assert _not_judged("doorstop", _CHECK_UNREVIEWED_FAILED) in result.stdout
    for stage in ("check_suspect_links", "check_text_citations", "check_headers", "check_citations"):
        assert _not_judged(stage, _TREE_DID_NOT_LOAD) in result.stdout
    assert combined.count("not judged") == 5
    _no_traceback(result)
    _no_wisekiosk_reference(combined)


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


def _csl_both_dangling_and_stale(repo: Path) -> None:
    # One inactive item carrying two links: one gone stale (its parent mutated), one naming a
    # parent that was never there -- both report sections fire together.
    _set_fields(repo / TST1, active=False)
    stale_stamp = _load(repo / TST1)["links"][0]["SRS001"]
    _reviewed_edit(repo, repo / SRS1, "SRS001", text="The software shall do yet another mutated thing.\n")
    _set_fields(repo / TST1, links=[{"SRS001": stale_stamp}, {"SRS999": stale_stamp}])


def _csl_unstamped_link_outside_root(repo: Path) -> None:
    # check_unreviewed walks only `root`; check_suspect_links and doorstop itself walk from the
    # working directory, so a document outside `root` is invisible to stage 1 but not to stage 2
    # or 3 -- the one place an inactive item's never-stamped link is check_suspect_links' own to
    # see, not check_unreviewed's.
    document = minimal_tree.add_document(repo, "extra/qa", "QA", parent="TST")
    path = document / "QA001.yml"
    _dump(
        path,
        {
            "active": False, "derived": False, "header": "Outside root, unstamped link",
            "level": 1.0, "links": ["TST001"], "normative": True, "rationale": "",
            "ref": "", "reviewed": None, "status": "accepted",
            "text": "Lives outside --root; its link to TST001 carries no stamp.",
            "verification-justification": "irrelevant to this stage",
            "verification-method": "test",
        },
    )
    assert _load(path)["links"] == ["TST001"]


# -- doorstop (the --error-all --no-reformat subprocess) -------------------------------------------


def _doorstop_active_orphan_link(repo: Path) -> None:
    stamp = _load(repo / SRS1)["links"][0]["SYS001"]
    _set_fields(repo / SRS1, links=[{"SYS999": stamp}])


# -- check_method_consistency: multi-step seeds --------------------------------------------------


def _mc_parent_understates_with_justification_pass(repo: Path) -> None:
    # SRS001 understating TST001 (test) at inspection, with a justification, is the legitimate
    # case -- but lowering SRS001 alone would leave SYS001 (unchanged, at test) *overstating*
    # relative to its now-inspection child. SYS001 drops to inspection too, keeping the SYS/SRS
    # pair consistent (equal ranks), so only the SRS/TST pair exercises the exception.
    _reviewed_edit(repo, repo / SYS1, "SYS001", clears=("SRS001",), **{"verification-method": "inspection"})
    _reviewed_edit(
        repo, repo / SRS1, "SRS001", clears=("TST001",),
        **{"verification-method": "inspection", "verification-justification": "Settles a residual the TST child does not carry."},
    )


def _mc_normative_false_pass(repo: Path) -> None:
    minimal_tree.add_reviewed_item(
        repo, "docs/requirements/srs", "SRS",
        header="Extra non-normative note", text="An orientation note, not an obligation.",
        verification_method="", verification_justification="",
    )
    _set_fields(repo / "docs/requirements/srs/SRS002.yml", normative=False)
    _run_review(repo, "SRS002")


# -- check_citations: Markdown seeds and multi-step seeds ------------------------------------------


def _cc_md(repo: Path, relpath: str, text: str) -> Path:
    """Writes and `git add`s a Markdown file -- `git ls-files` sees a staged path with no commit
    needed."""
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    result = _git(repo, "add", relpath)
    assert result.returncode == 0, result.stderr
    assert relpath in _git(repo, "ls-files", "-z", relpath).stdout.split("\0")
    return path


def _cc_untracked_md(repo: Path, relpath: str, text: str) -> Path:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    assert relpath not in _git(repo, "ls-files", relpath).stdout.split()
    return path


def _cc_inactive_item_cited_pass(repo: Path) -> None:
    """An inactive item still carries a header, and `_iter()` includes it -- the fold's header map
    is not active-only."""
    uid = minimal_tree.add_reviewed_item(
        repo, "docs/requirements/srs", "SRS",
        header="Extra inactive note", text="An inactive item, included in the citation's header map.",
        verification_method="", verification_justification="",
        parent_uid="SYS001",
    )
    _set_fields(repo / f"docs/requirements/srs/{uid}.yml", active=False, normative=False)
    _cc_md(repo, "notes.md", f"See {uid}<!-- Extra inactive note --> for background.\n")


def _cc_rmtree_git(repo: Path) -> None:
    shutil.rmtree(repo / ".git")
    assert not (repo / ".git").exists()


def _cc_silo_removed_and_no_git(repo: Path) -> None:
    _cu_silo_removed(repo)
    _cc_rmtree_git(repo)


def _cc_single_problem(needle: str) -> Callable:
    """Exactly one indented finding line in stderr -- each is printed `  {problem}`, so a second,
    unwanted report (e.g. an existence check firing after a case report should have short-circuited
    it) would add a second such line."""

    def check(result: subprocess.CompletedProcess) -> None:
        _must_fail_at("check_citations", has=needle)(result)
        assert result.stderr.count("\n  ") == 1

    return check


def _cc_outside_git_working_copy_not_judged(result: subprocess.CompletedProcess) -> None:
    """check_unreviewed and check_suspect_links need no VCS and pass; doorstop's own CLI calls
    vcs.find_root and fails cleanly, with no traceback; check_citations is gated on the missing
    working copy."""
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Every item and every link carries a review fingerprint." in combined
    assert "no working copy found from" in combined
    assert _not_judged("check_citations", _NOT_A_GIT_WORKING_COPY) in result.stdout
    assert combined.count("not judged") == 1
    _no_traceback(result)
    _no_wisekiosk_reference(combined)


def _cc_both_preconditions_tree_did_not_load_wins(result: subprocess.CompletedProcess) -> None:
    """Both of check_citations' preconditions fail at once; the reason printed is the first in the
    plan's listed order -- the tree not loading, not the missing working copy."""
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "holds no document — missing, renamed, or deleted." in combined
    assert _not_judged("check_citations", _TREE_DID_NOT_LOAD) in result.stdout
    assert _NOT_A_GIT_WORKING_COPY not in combined
    assert combined.count("not judged") == 5
    _no_traceback(result)
    _no_wisekiosk_reference(combined)


CASES: list[_Case] = [
    # check_unreviewed
    _Case("cu-reviewed-deleted", lambda r: _delete_key(r / SYS1, "reviewed"),
          _must_fail_at("check_unreviewed", has=("carry no review fingerprint", "SYS001"))),
    _Case("cu-reviewed-true-bool", lambda r: _set_fields(r / SYS1, reviewed=True),
          _must_fail_at("check_unreviewed", has="carry no review fingerprint")),
    _Case("cu-reviewed-empty-string", lambda r: _set_fields(r / SYS1, reviewed=""),
          _must_fail_at("check_unreviewed", has="carry no review fingerprint")),
    _Case("cu-yaml-suffix-unreviewed",
          lambda r: _raw_unreviewed_item(r / "docs/requirements/sys", "SYS002", "Extra", "Extra item.", ".yaml"),
          _must_fail_at("check_unreviewed", has=("carry no review fingerprint", "SYS002"))),
    _Case("cu-link-stamp-copied-by-hand", lambda r: _delete_key(r / SRS1, "reviewed"),
          _must_fail_at("check_unreviewed", has=("carry no review fingerprint", "SRS001"))),
    _Case("cu-silo-removed", _cu_silo_removed,
          _cu_silo_removed_leaves_doorstop_stages_not_judged),
    _Case("cu-silo-renamed", _cu_silo_renamed,
          _must_fail_at("check_unreviewed", has="holds no document — missing, renamed, or deleted.")),
    # The carried-over breakdown only ever names SYS/SRS/TST-prefixed UIDs (the fixed tuple in
    # check_unreviewed.py); a nested document's own prefix is never named, only counted.
    _Case("cu-nested-item-unreviewed", _cu_nested_item_unreviewed,
          _must_fail_at("check_unreviewed", has="carry no review fingerprint")),
    _Case("cu-all-silos-removed", _cu_all_silos_removed,
          _must_fail_at("check_unreviewed", has="holds no document — missing, renamed, or deleted.")),
    _Case("cu-silo-emptied", _cu_silo_emptied,
          _must_fail_at("check_unreviewed", has="yielded no item — this check read none of it.")),
    _Case("cu-nested-no-items", _cu_nested_no_items,
          _must_fail_at("check_unreviewed", has="yielded no item — this check read none of it.")),
    _Case("cu-two-nested-share-dirname-one-empty", _cu_two_nested_share_dirname,
          _must_fail_at("check_unreviewed", has="yielded no item — this check read none of it.")),
    _Case("cu-fourth-tier-and-nested-pass", _cu_fourth_tier_and_nested_pass, _must_pass),
    _Case("cu-venv-doorstop-yml-pass", _cu_venv_doorstop_yml_pass, _must_pass),

    # check_suspect_links
    _Case("csl-parent-mutated-stale", _csl_parent_mutated_stale,
          _must_fail_at("check_suspect_links", has=("are suspect", "TST001", "SRS001"))),
    _Case("csl-inactive-dangling-parent", _csl_inactive_dangling_parent,
          _must_fail_at("check_suspect_links", has=("name a parent the tree does not hold", "SRS999"))),
    _Case("csl-both-dangling-and-stale", _csl_both_dangling_and_stale,
          _must_fail_at("check_suspect_links", has=("name a parent the tree does not hold", "are suspect", "SRS999", "SRS001"))),
    _Case("csl-unstamped-link-outside-root-is-not-this-stages-finding", _csl_unstamped_link_outside_root,
          _check_unstamped_link_outside_root_passes_stage_two_then_fails_at_doorstop),

    # doorstop
    _Case("doorstop-active-orphan-link", _doorstop_active_orphan_link,
          _must_fail_at("doorstop", has="no item with UID: SYS999")),

    # check_method_consistency
    _Case("mc-blanked-justification",
          lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), **{"verification-justification": ""}),
          _must_fail_at("check_method_consistency", has=("carry no verification-justification", "SYS001"))),
    _Case("mc-parent-overstates",
          lambda r: _reviewed_edit(r, r / TST1, "TST001", **{"verification-method": "inspection"}),
          _must_fail_at("check_method_consistency", has=("above its least-decidable child", "SRS001"))),
    _Case("mc-parent-understates-no-justification",
          lambda r: _reviewed_edit(r, r / SRS1, "SRS001", clears=("TST001",), **{"verification-method": "inspection", "verification-justification": ""}),
          _must_fail_at("check_method_consistency", has=("below every child with no verification-justification", "SRS001"))),
    # The one legitimate exception docs/requirements/README.md's "Choosing a verification method"
    # names: a parent below its least-decidable child, excused by its own verification-justification.
    _Case("mc-parent-understates-with-justification-pass",
          _mc_parent_understates_with_justification_pass,
          _must_pass),
    _Case("mc-capitalised-method",
          lambda r: _reviewed_edit(r, r / TST1, "TST001", **{"verification-method": "Test"}),
          _must_fail_at("check_method_consistency", has=("carry an unrecognised verification-method", "'Test' is not one of"))),
    _Case("mc-typo-method",
          lambda r: _reviewed_edit(r, r / TST1, "TST001", **{"verification-method": "tset"}),
          _must_fail_at("check_method_consistency", has=("carry an unrecognised verification-method", "'tset' is not one of"))),
    _Case("mc-method-key-deleted", lambda r: _reviewed_delete(r, r / TST1, "TST001", "verification-method"),
          _must_fail_at("check_method_consistency", has=("carry an unrecognised verification-method", "TST001"))),
    _Case("mc-normative-false-pass", _mc_normative_false_pass, _must_pass),

    # check_text_citations
    _Case("tc-identifier-in-text",
          lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), text="The system shall match SRS001 exactly.\n"),
          _must_fail_at("check_text_citations", has=("cite another item in `text`", "SYS001 -> SRS001"))),
    _Case("tc-lowercase-identifier-in-text",
          lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), text="The system shall match srs001 exactly.\n"),
          _must_fail_at("check_text_citations", has="cite another item in `text`")),

    # check_headers (header is outside the review fingerprint -- no re-review needed)
    _Case("ch-emptied-header", lambda r: _set_fields(r / SYS1, header=""),
          _must_fail_at("check_headers", has=("SYS001", "has no header"))),
    _Case("ch-slash-in-header", lambda r: _set_fields(r / SYS1, header="Sample system/need"),
          _must_fail_at("check_headers", has=("outside the permitted set", "'/'"))),
    _Case("ch-en-dash-in-header", lambda r: _set_fields(r / SYS1, header="Sample system–need"),
          _must_fail_at("check_headers", has="outside the permitted set")),
    _Case("ch-nbsp-in-header", lambda r: _set_fields(r / SYS1, header=" Sample system need"),
          _must_fail_at("check_headers", has="outside the permitted set")),
    _Case("ch-folded-header-pass", lambda r: _set_fields(r / SYS1, header="Sample system\nneed, folded"),
          _must_pass),
    _Case("ch-duplicate-header", lambda r: _set_fields(r / TST1, header="SAMPLE SOFTWARE REQUIREMENT"),
          _must_fail_at("check_headers", has=("carry the same header", "SRS001", "TST001"))),
    _Case("ch-prefix-header", lambda r: _set_fields(r / SRS1, header="Sample verif"),
          _must_fail_at("check_headers", has=("header is a prefix of", "SRS001", "TST001"))),

    # check_citations -- the requirement half of WiseKiosk's scripts/check-citations.py; the ADR
    # half is check-adrs'.
    _Case("cc-tracked-claude-md-excluded-pass",
          lambda r: _cc_md(r, ".claude/notes.md", "SYS999 names nothing, but .claude/ is excluded.\n"),
          _must_pass),
    _Case("cc-untracked-md-fails",
          lambda r: _cc_untracked_md(r, "notes.md", "Just a note.\n"),
          _must_fail_at("check_citations", has=("notes.md", "untracked, so this check cannot read it"))),
    _Case("cc-untracked-claude-md-pass",
          lambda r: _cc_untracked_md(r, ".claude/notes.md", "Just a note.\n"),
          _must_pass),
    _Case("cc-inactive-item-cited-pass", _cc_inactive_item_cited_pass, _must_pass),
    _Case("cc-word-containing-identifier-pass",
          lambda r: _cc_md(r, "notes.md", "See SYS0019 for an unrelated serial number.\n"),
          _must_pass),
    _Case("cc-miscased-identifier-with-fabricated-header-one-report",
          lambda r: _cc_md(r, "notes.md", "srs001<!-- A header this item does not carry --> is mentioned here.\n"),
          _cc_single_problem("is not uppercase — an identifier is cited as SRS001")),
    _Case("cc-mixedcase-identifier-fails",
          lambda r: _cc_md(r, "notes.md", "SrS001 is mentioned here.\n"),
          _must_fail_at("check_citations", has="is not uppercase")),
    _Case("cc-citation-names-no-item-fails",
          lambda r: _cc_md(r, "notes.md", "SRS999 names nothing real.\n"),
          _must_fail_at("check_citations", has=("SRS999", "names no item in the requirements tree"))),
    _Case("cc-yml-suffix-on-missing-item-still-fails",
          lambda r: _cc_md(r, "notes.md", "See SYS999.yml for the source.\n"),
          _must_fail_at("check_citations", has=("SYS999", "names no item in the requirements tree"))),
    _Case("cc-yml-suffix-exemption-pass",
          lambda r: _cc_md(r, "notes.md", "See SYS001.yml for the source.\n"),
          _must_pass),
    _Case("cc-yml-suffix-exemption-in-rationale-pass",
          lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), rationale="See SRS001.yml for the source.\n"),
          _must_pass),
    _Case("cc-backtick-wrapped-identifier-pass",
          lambda r: _cc_md(r, "notes.md", "The item `SRS001`<!-- Sample software requirement --> is linked here.\n"),
          _must_pass),
    _Case("cc-no-header-comment-fails",
          lambda r: _cc_md(r, "notes.md", "SRS001 is mentioned here with no comment.\n"),
          _must_fail_at("check_citations", has=("SRS001", "carries no header comment"))),
    _Case("cc-whitespace-before-comment-fails",
          lambda r: _cc_md(r, "notes.md", "SRS001 <!-- Sample software requirement --> is mentioned here.\n"),
          _must_fail_at("check_citations", has=("SRS001", "whitespace separates the identifier from its header"))),
    _Case("cc-unterminated-comment-fails",
          lambda r: _cc_md(r, "notes.md", "SRS001<!-- never closes\n"),
          _must_fail_at("check_citations", has=("SRS001", "opens a header comment that never closes"))),
    _Case("cc-wrong-header-fails",
          lambda r: _cc_md(r, "notes.md", "SRS001<!-- Wrong header text --> is mentioned here.\n"),
          _must_fail_at("check_citations", has="expected the item's header 'Sample software requirement', found 'wrong header text'")),
    _Case("tc-identifier-in-rationale-pass",
          lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), rationale="Decomposed by SRS001<!-- Sample software requirement -->, which is fine to name here.\n"),
          _must_pass),
    _Case("cc-header-split-across-blank-line-pass",
          lambda r: _cc_md(r, "notes.md", "SRS001<!-- Sample software\n\nrequirement --> is mentioned here.\n"),
          _must_pass),
    _Case("cc-fenced-citation-hidden-pass",
          lambda r: _cc_md(r, "notes.md", "Example:\n\n```\nSYS999 is just an example, not a real citation.\n```\n"),
          _must_pass),
    _Case("cc-unclosed-fence-fails-once",
          lambda r: _cc_md(r, "notes.md", "```\nSYS999 would be a problem if read.\n"),
          _cc_single_problem("notes.md  a code fence is never closed, so everything below it goes unread")),
    _Case("cc-comment-interrupts-paragraph-fails",
          lambda r: _cc_md(r, "notes.md", "A paragraph of plain prose.\n<!-- a stray comment -->\n"),
          _must_fail_at("check_citations", has="a comment opens this line, splitting the paragraph above it")),
    # The script's line formula (`item_sources`' first line starting "{field}:", plus 2) assumes a
    # block scalar; Doorstop dumps a short, special-character-free rationale as a plain scalar on
    # the key line itself, so the formula reports one line past the actual content (line 9, not the
    # real line 8) -- lift-and-shift carries this exactly, a documented gap, not a fix.
    _Case("cc-item-field-citation-line-number-off-by-one",
          lambda r: _reviewed_edit(r, r / SYS1, "SYS001", clears=("SRS001",), rationale="See SRS999 for details."),
          _must_fail_at("check_citations", has=("docs/requirements/sys/SYS001.yml:9", "SRS999", "names no item in the requirements tree"))),
    # R18: the `.yml`-suffix exemption (cc-yml-suffix-exemption-pass, above) does not extend to
    # `.yaml` -- the literal prefix check is `.yml` only, so a `.yaml`-suffixed mention still falls
    # through to the header-comment rules and fails for carrying none.
    _Case("cc-yaml-suffix-not-exempt-fails",
          lambda r: _cc_md(r, "notes.md", "See SYS001.yaml for the source.\n"),
          _must_fail_at("check_citations", has=("SYS001", "carries no header comment"))),
    # R20: annotation() strips a leading run of backtick, 's or ' before testing for the opening
    # comment. cc-backtick-wrapped-identifier-pass covers the backtick; these cover the other two.
    _Case("cc-clitic-apostrophe-s-pass",
          lambda r: _cc_md(r, "notes.md", "SRS001's<!-- Sample software requirement --> is mentioned here.\n"),
          _must_pass),
    _Case("cc-clitic-apostrophe-pass",
          lambda r: _cc_md(r, "notes.md", "SRS001'<!-- Sample software requirement --> is mentioned here.\n"),
          _must_pass),
    # R26: normalise() folds a line break (with an optional blockquote marker continuing it) to a
    # single space, then splits on any run of whitespace and casefolds -- so a header carried across
    # a blockquote continuation, or written with irregular interior whitespace, or differing from the
    # item's header only in case, all still match.
    _Case("cc-header-blockquote-continuation-pass",
          lambda r: _cc_md(r, "notes.md", "SRS001<!-- Sample software\n> requirement --> is mentioned here.\n"),
          _must_pass),
    _Case("cc-header-whitespace-run-pass",
          lambda r: _cc_md(r, "notes.md", "SRS001<!--  Sample   software requirement  --> is mentioned here.\n"),
          _must_pass),
    _Case("cc-header-case-only-difference-pass",
          lambda r: _cc_md(r, "notes.md", "SRS001<!-- SAMPLE SOFTWARE REQUIREMENT --> is mentioned here.\n"),
          _must_pass),
    # R27: a `~~~` fence blanks and hides a citation exactly as a ``` fence does
    # (cc-fenced-citation-hidden-pass); and the two fence characters do not close each other, so a
    # ``` opened and only ever followed by a `~~~` line stays open to EOF -- the same unclosed-fence
    # finding as cc-unclosed-fence-fails-once.
    _Case("cc-tilde-fence-hidden-pass",
          lambda r: _cc_md(r, "notes.md", "Example:\n\n~~~\nSYS999 is just an example, not a real citation.\n~~~\n"),
          _must_pass),
    _Case("cc-backtick-fence-not-closed-by-tilde-fails-once",
          lambda r: _cc_md(r, "notes.md", "```\nSYS999 would be a problem if read.\n~~~\n"),
          _cc_single_problem("notes.md  a code fence is never closed, so everything below it goes unread")),
    # R29: the must-pass partner of cc-comment-interrupts-paragraph-fails -- a comment opening a
    # line is only a finding when the line above it is non-blank -- and the same finding reached via
    # a blockquote continuation, where QUOTE-stripping is what exposes the interruption.
    _Case("cc-comment-after-blank-line-pass",
          lambda r: _cc_md(r, "notes.md", "A paragraph of plain prose.\n\n<!-- a stray comment -->\n"),
          _must_pass),
    _Case("cc-blockquote-continuation-comment-interrupts-fails",
          lambda r: _cc_md(r, "notes.md", "> A paragraph of plain prose.\n> <!-- a stray comment -->\n"),
          _must_fail_at("check_citations", has="a comment opens this line, splitting the paragraph above it")),
    # R5: a tracked Markdown path holding a space is judged, not an uncaught traceback -- the
    # valid citation in it resolves cleanly, and the bad one is still reported, by its full path.
    _Case("cc-tracked-md-path-with-space-judged-not-crashed",
          lambda r: _cc_md(r, "docs/a b.md", "SRS001<!-- Sample software requirement --> is fine. SRS999 names nothing real.\n"),
          _cc_single_problem(("docs/a b.md", "SRS999", "names no item in the requirements tree"))),
    _Case("cc-outside-git-working-copy-not-judged",
          _cc_rmtree_git,
          _cc_outside_git_working_copy_not_judged),
    _Case("cc-both-preconditions-tree-did-not-load-wins",
          _cc_silo_removed_and_no_git,
          _cc_both_preconditions_tree_did_not_load_wins),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: _Case, repo: Path) -> None:
    case.seed(repo)
    result = _run_check(repo, "--root", "docs/requirements")
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
def test_report_proposed_lines(repo: Path, seed, must_contain: tuple) -> None:
    if seed is not None:
        seed(repo)

    result = _run_check(repo, "--root", "docs/requirements")

    _must_pass(result)
    for text in must_contain:
        assert text in result.stdout


# -- --root: resolution against the working directory, never the package's own location -----------


def test_missing_root_fails_at_check_unreviewed_with_the_resolved_path(tmp_path: Path) -> None:
    repo = minimal_tree.init_repo(tmp_path / "repo")
    assert not (repo / "docs/requirements").exists()

    result = _run_check(repo, "--root", "docs/requirements")

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    for stage in STAGES:
        assert _stage_header(stage) in result.stdout
    resolved = repo / "docs/requirements"
    for silo in ("sys", "srs", "tst"):
        assert f"{resolved / silo}/ holds no document — missing, renamed, or deleted." in combined
    assert _not_judged("doorstop", _CHECK_UNREVIEWED_FAILED) in result.stdout
    for stage in ("check_suspect_links", "check_text_citations", "check_headers", "check_citations"):
        assert _not_judged(stage, _TREE_DID_NOT_LOAD) in result.stdout
    assert combined.count("not judged") == 5
    _no_traceback(result)


def test_absolute_root_is_accepted(repo: Path) -> None:
    _must_pass(_run_check(repo, "--root", str(repo / "docs/requirements")))


def test_default_root_is_docs_requirements(repo: Path) -> None:
    _must_pass(_run_check(repo))


def test_check_citations_success_line_on_the_baseline_tree(repo: Path) -> None:
    """The baseline tree's one real citation (SRS001's rationale, citing TST001) exercises
    check_citations' pass path for real rather than vacuously."""
    result = _run_check(repo, "--root", "docs/requirements")

    _must_pass(result)
    assert "Every citation resolves, and every requirement citation carries its item's header." in result.stdout


# -- req_sha_item_validator: the TST extension hook --------------------------------------------


def test_req_sha_item_validator_fails_when_referenced_file_changed_since_review(repo: Path) -> None:
    (repo / "verified-file.txt").write_text("verified behaviour\n")
    _set_fields(repo / TST1, references=[{"path": "verified-file.txt", "type": "file"}])
    _run_review(repo, "TST001")
    assert _load(repo / TST1)["references"][0].get("sha")
    (repo / "verified-file.txt").write_text("a different line\n")

    result = _run_check(repo, "--root", "docs/requirements")

    _must_fail_at("doorstop", has="referenced file changed since review: verified-file.txt")(result)


def test_req_sha_item_validator_no_sha_recorded_backstopped_by_doorstop_itself(repo: Path) -> None:
    (repo / "untracked-reference.txt").write_text("not yet reviewed against\n")
    _set_fields(repo / TST1, references=[{"path": "untracked-reference.txt", "type": "file"}])
    assert _load(repo / TST1)["references"][0].get("sha") is None

    result = _run_check(repo, "--root", "docs/requirements")

    assert "referenced file changed since review" not in (result.stdout + result.stderr)
    _must_fail_at("doorstop", has="unreviewed changes")(result)


# -- Order: check_unreviewed runs before Doorstop ever validates, so its own failure -- gating
# doorstop rather than letting it run -- and a clean pass both leave every item file byte-identical.
# -------------------------------------------------------------------------------------------------


def _item_bytes(repo: Path) -> dict[str, bytes]:
    return {relpath: (repo / relpath).read_bytes() for relpath in (SYS1, SRS1, TST1)}


def test_failing_at_check_unreviewed_leaves_the_tree_byte_identical(repo: Path) -> None:
    """check_unreviewed fails on a plain unreviewed item, not a missing or empty document, so the
    tree still loads: only doorstop is gated (on check_unreviewed's own failure), and every other
    stage runs and judges normally."""
    _delete_key(repo / SYS1, "reviewed")
    before = _item_bytes(repo)

    result = _run_check(repo, "--root", "docs/requirements")

    _must_fail_at("check_unreviewed")(result)
    combined = result.stdout + result.stderr
    assert _not_judged("doorstop", _CHECK_UNREVIEWED_FAILED) in result.stdout
    assert combined.count("not judged") == 1
    assert _item_bytes(repo) == before


def test_passing_tree_is_byte_identical_after_the_run(repo: Path) -> None:
    before = _item_bytes(repo)

    result = _run_check(repo, "--root", "docs/requirements")

    _must_pass(result)
    assert _item_bytes(repo) == before


# -- check_suspect_links only examines inactive items: an active parent's own suspect link is
# Doorstop's own problem one stage later, not this stage's.
# -------------------------------------------------------------------------------------------------


def test_suspect_links_passes_for_an_active_parent_mutation_which_doorstop_then_fails(repo: Path) -> None:
    _set_fields(repo / SYS1, text="The system shall do a mutated thing.\n")

    result = _run_check(repo, "--root", "docs/requirements")

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert _stage_header("check_suspect_links") in combined
    assert "Every inactive item's links resolve and match the parents they were reviewed against." in combined
    assert _stage_header("doorstop") in combined
    for stage in STAGES[3:]:
        assert _stage_header(stage) in result.stdout
    assert "not judged" not in combined
    _no_traceback(result)
    _no_wisekiosk_reference(combined)


# -- Test plumbing: a copied tree matches a fresh build, and each case gets its own copy ----------


def _working_tree_files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_copied_tree_matches_fresh_build(repo: Path, tmp_path: Path) -> None:
    """`repo` is a copy of the session's one baseline tree. Built fresh here instead, it must come
    out byte for byte the same, doorstop review stamps included -- the real `doorstop` CLI's stamps
    are a content hash, not a timestamp."""
    fresh = minimal_tree.init_repo(tmp_path / "fresh")
    minimal_tree.build(fresh)

    assert _working_tree_files(repo) == _working_tree_files(fresh)
    # The raw `.git/index` is not compared: it carries stat data that differs between the two
    # repositories even when their tracked content is identical.
    assert _git(repo, "ls-files", "-s").stdout == _git(fresh, "ls-files", "-s").stdout


def test_each_case_gets_its_own_copy(repo: Path, baseline_tree: Path, tmp_path: Path) -> None:
    assert repo.is_relative_to(tmp_path)
    assert not repo.is_relative_to(baseline_tree)

    (repo / SYS1).unlink()

    assert not (repo / SYS1).exists()
    assert (baseline_tree / SYS1).exists()


def test_two_independent_failures_in_one_run_are_both_reported(repo: Path) -> None:
    """check_method_consistency fails on SYS001, check_headers fails on TST001 -- two unrelated
    items, neither failure a precondition for the other -- and run-every-stage reports both in one
    run rather than hiding the second behind the first."""
    _reviewed_edit(repo, repo / SYS1, "SYS001", clears=("SRS001",), **{"verification-justification": ""})
    _set_fields(repo / TST1, header="")

    result = _run_check(repo, "--root", "docs/requirements")

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    for stage in STAGES:
        assert _stage_header(stage) in result.stdout
    assert "carry no verification-justification" in combined
    assert "SYS001" in combined
    assert "has no header" in combined
    assert "TST001" in combined
    assert "not judged" not in combined
    _no_traceback(result)
    _no_wisekiosk_reference(combined)
