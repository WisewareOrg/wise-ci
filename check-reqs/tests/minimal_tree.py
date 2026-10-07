"""Builds the clean minimal Doorstop tree check-reqs's tests run against, and the extra
documents some cases add beside it.

`build(directory)` writes `docs/requirements/{sys,srs,tst}` in the consumers' shape -- the three
`.doorstop.yml`s (`digits: 3`, `sep: ''`, the `tst` extensions, the one-line validator shim) and one
reviewed, accepted item per tier (header, text, `verification-method: test`,
`verification-justification`, `rationale`), SRS linked to SYS and TST linked to SRS, every stamp
written by the real `doorstop` CLI's `clear` and `review` commands. `directory` must already lie
inside a git working copy.

`add_document(directory, relpath, prefix, parent=None)` writes one more `.doorstop.yml` beside the
three, with no items -- a document with no items, or an inert marker such as a tool directory's own
config file.

`add_reviewed_item(directory, relpath, *, header, text, ..., parent_uid=None)` adds, fills, links,
clears and reviews one further item in a document `add_document` or `build` already created, and
returns its UID.

Run as a script with one argument, the directory to build into, it calls `build` alone.
"""

import subprocess
import sys
from pathlib import Path

import yaml

DOORSTOP = Path(sys.executable).with_name("doorstop")

_SETTINGS = {"digits": 3, "itemformat": "yaml", "sep": ""}
_ATTRIBUTES = {
    "defaults": {
        "status": "proposed",
        "verification-method": "",
        "verification-justification": "",
        "rationale": "",
    },
    "reviewed": ["rationale", "verification-method", "verification-justification"],
}
_TST_EXTENSIONS = {"item_sha_required": True, "item_validator": ".req_sha_item_validator.py"}
_SHIM = "from check_reqs.req_sha_item_validator import item_validator\n"


def _run(directory: Path, *args: str) -> None:
    result = subprocess.run(
        [str(DOORSTOP), *args], cwd=directory, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"doorstop {' '.join(args)} in {directory} failed:\n{result.stdout}{result.stderr}"
        )


def add_document(directory: Path, relpath: str, prefix: str, *, parent: str | None = None) -> Path:
    """Writes `relpath/.doorstop.yml` under `directory`; the document holds no items."""
    document = directory / relpath
    document.mkdir(parents=True, exist_ok=True)
    settings = dict(_SETTINGS, prefix=prefix)
    if parent:
        settings["parent"] = parent
    config: dict = {"settings": settings}
    if prefix == "TST":
        config["extensions"] = dict(_TST_EXTENSIONS)
        (document / ".req_sha_item_validator.py").write_text(_SHIM)
    config["attributes"] = _ATTRIBUTES
    (document / ".doorstop.yml").write_text(yaml.safe_dump(config, sort_keys=False))
    return document


def add_reviewed_item(
    directory: Path,
    relpath: str,
    prefix: str,
    *,
    header: str,
    text: str,
    verification_method: str = "test",
    verification_justification: str = "",
    rationale: str = "",
    parent_uid: str | None = None,
) -> str:
    """Adds one item to the document at `relpath` (by its `prefix`), fills its fields, links it to
    `parent_uid` if given, and clears and reviews it so every stamp is Doorstop's own."""
    before = {p.stem for p in (directory / relpath).glob("*.yml") if not p.stem.startswith(".")}
    _run(directory, "add", prefix)
    added = {p.stem for p in (directory / relpath).glob("*.yml") if not p.stem.startswith(".")}
    uid = next(iter(added - before))

    item_path = directory / relpath / f"{uid}.yml"
    data = yaml.safe_load(item_path.read_text())
    data["header"] = header
    data["text"] = text
    data["status"] = "accepted"
    data["verification-method"] = verification_method
    data["verification-justification"] = verification_justification
    data["rationale"] = rationale
    item_path.write_text(yaml.safe_dump(data, sort_keys=False))

    if parent_uid:
        _run(directory, "link", uid, parent_uid)
        _run(directory, "clear", uid)
    _run(directory, "review", uid)
    return uid


def build(directory: Path) -> None:
    """Builds the three-tier minimal tree, fully reviewed and cleared, under `directory`."""
    add_document(directory, "docs/requirements/sys", "SYS")
    add_document(directory, "docs/requirements/srs", "SRS", parent="SYS")
    add_document(directory, "docs/requirements/tst", "TST", parent="SRS")

    sys_uid = add_reviewed_item(
        directory,
        "docs/requirements/sys",
        "SYS",
        header="Sample system need",
        text="The system shall do the sample thing.",
        verification_justification="Settled by its children.",
        rationale="Exists to give the tree a reviewable SYS item.",
    )
    srs_uid = add_reviewed_item(
        directory,
        "docs/requirements/srs",
        "SRS",
        header="Sample software requirement",
        text="The software shall do the sample thing.",
        verification_justification="Settled by its TST child.",
        parent_uid=sys_uid,
    )
    add_reviewed_item(
        directory,
        "docs/requirements/tst",
        "TST",
        header="Sample verification",
        text="Asserts the sample thing happens.",
        verification_justification="Settles the sample obligation directly.",
        parent_uid=srs_uid,
    )


if __name__ == "__main__":
    build(Path(sys.argv[1]))
