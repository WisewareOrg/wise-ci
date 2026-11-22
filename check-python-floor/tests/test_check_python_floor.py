"""Specifies check-python-floor/check_python_floor/__init__.py, the org Python floor, and its output interface.

The README (check-python-floor/README.md) and ADR 0002 rev 1 state them: the exact
allowlist for `[tool.ruff]`, the three absent tables, the `requires-python` lower bound, the root
pyproject.toml a repo tracking `.py` must have, no tracked side configuration (`ruff.toml`,
`.ruff.toml`, `ty.toml`, a non-root `[tool.ruff]` or `[tool.ty]`), one stderr line per violation in
a fixed order and form, the pass line, and the "no Python" pass when no `.py` is tracked.

Each case builds a real, isolated git repository in a temporary directory (floor_repo.py) and runs
the installed `check-python-floor` console script against it as a subprocess, working directory the
repository (docs/TESTING.md "Real dependencies where possible"). Nothing defective is committed to
this repository.
"""

import subprocess
import sys
from pathlib import Path

import check_python_floor
import floor_repo
import pytest
from floor_repo import pyproject

SCRIPT = Path(sys.executable).with_name("check-python-floor")

PASS_LINE = "check-python-floor: pyproject.toml meets the floor."
NO_PYTHON_LINE = "check-python-floor: no Python — no tracked .py files."
SELECT_EXPECTED = "E, F, W, I, UP, B, SIM, D, D417"


def _run(repo: Path) -> tuple[int, list[str], list[str]]:
    """Run the check in a repository.

    Args:
        repo: The repository to run in.

    Returns:
        The exit status, the non-blank stdout lines and the non-blank stderr lines.
    """
    result = subprocess.run([str(SCRIPT)], cwd=repo, env=floor_repo.env(), capture_output=True, text=True)
    return result.returncode, _lines(result.stdout), _lines(result.stderr)


def _lines(text: str) -> list[str]:
    """Split text into its non-blank lines.

    Args:
        text: The text.

    Returns:
        The lines with content.
    """
    return [line for line in text.splitlines() if line.strip()]


CONFORMANT = {
    "baseline": pyproject(),
    "src is any value": pyproject(src='"."'),
    "src is any list": pyproject(src='["a", "b"]'),
    "requires-python above the floor": pyproject(requires=">=3.13"),
    "requires-python with an upper bound": pyproject(requires=">=3.12,<4"),
    "select in another order": pyproject(select=list(reversed(floor_repo.CONFORMANT_SELECT))),
    "select with a duplicate": pyproject(select=[*floor_repo.CONFORMANT_SELECT, "E"]),
    "other tool tables are not the floor's concern": pyproject(
        tail='[tool.pytest.ini_options]\naddopts = ["-q"]\n\n[tool.uv]\npackage = false\n'
    ),
}


@pytest.mark.parametrize("text", CONFORMANT.values(), ids=CONFORMANT.keys())
def test_conformant_pyproject_passes_with_the_pass_line(tmp_path: Path, text: str) -> None:
    """A conformant pyproject.toml passes with the pass line and nothing on stderr.

    Args:
        tmp_path: A fresh temporary directory.
        text: The pyproject.toml text.
    """
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", text))
    assert (status, out, err) == (0, [PASS_LINE], [])


# (id, pyproject text, the one stderr line)
VIOLATIONS = [
    (
        "line-length differs",
        pyproject(line_length=100),
        "pyproject.toml: [tool.ruff] line-length: expected 120, found 100",
    ),
    (
        "extra ruff key target-version",
        pyproject(ruff_extra='target-version = "py312"\n'),
        "pyproject.toml: [tool.ruff] target-version: not allowed by the floor",
    ),
    (
        "extra ruff key exclude",
        pyproject(ruff_extra='exclude = ["x"]\n'),
        "pyproject.toml: [tool.ruff] exclude: not allowed by the floor",
    ),
    (
        "extra ruff lint key ignore",
        pyproject(lint_extra='ignore = ["E501"]\n'),
        "pyproject.toml: [tool.ruff.lint] ignore: not allowed by the floor",
    ),
    (
        "extra ruff pydocstyle key",
        pyproject(pydocstyle_extra='ignore-decorators = ["x"]\n'),
        "pyproject.toml: [tool.ruff.lint.pydocstyle] ignore-decorators: not allowed by the floor",
    ),
    (
        "ruff format table",
        pyproject(tail='[tool.ruff.format]\nquote-style = "single"\n'),
        "pyproject.toml: [tool.ruff.format] quote-style: not allowed by the floor",
    ),
    (
        "pydocstyle convention differs",
        pyproject(convention="numpy"),
        'pyproject.toml: [tool.ruff.lint.pydocstyle] convention: expected "google", found "numpy"',
    ),
    ("tool.ty present", pyproject(tail="[tool.ty]\n"), "pyproject.toml: [tool.ty] must be absent"),
    (
        "tool.interrogate present, however many keys",
        pyproject(tail="[tool.interrogate]\nfail-under = 100\nverbose = 2\n"),
        "pyproject.toml: [tool.interrogate] must be absent",
    ),
    (
        "tool.pydoclint present",
        pyproject(tail='[tool.pydoclint]\nstyle = "google"\n'),
        "pyproject.toml: [tool.pydoclint] must be absent",
    ),
    (
        "requires-python below 3.12",
        pyproject(requires=">=3.11"),
        'pyproject.toml: [project] requires-python: lower bound must be >= 3.12, found ">=3.11"',
    ),
    (
        "requires-python far below 3.12",
        pyproject(requires=">=3.9"),
        'pyproject.toml: [project] requires-python: lower bound must be >= 3.12, found ">=3.9"',
    ),
    (
        "requires-python absent",
        pyproject(requires=None),
        "pyproject.toml: [project] requires-python: missing, lower bound must be >= 3.12",
    ),
]


@pytest.mark.parametrize(("text", "line"), [v[1:] for v in VIOLATIONS], ids=[v[0] for v in VIOLATIONS])
def test_each_violation_is_exactly_one_stderr_line(tmp_path: Path, text: str, line: str) -> None:
    """Each single violation is exactly one stderr line and exit 1.

    Args:
        tmp_path: A fresh temporary directory.
        text: The pyproject.toml text.
        line: The expected stderr line.
    """
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", text))
    assert (status, out, err) == (1, [], [line])


SELECT_PREFIX = f"pyproject.toml: [tool.ruff.lint] select: expected {SELECT_EXPECTED} (any order), found "


@pytest.mark.parametrize(
    "select",
    [floor_repo.CONFORMANT_SELECT[:-1], [*floor_repo.CONFORMANT_SELECT, "C90"]],
    ids=["lacks D417", "has an extra rule"],
)
def test_select_that_differs_as_a_set_fails(tmp_path: Path, select: list[str]) -> None:
    """A `select` that differs from the required set, however ordered, is one violation line.

    Args:
        tmp_path: A fresh temporary directory.
        select: The `select` list written to the pyproject.toml.
    """
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", pyproject(select=select)))
    assert (status, out) == (1, [])
    assert len(err) == 1
    assert err[0].startswith(SELECT_PREFIX), err


def test_absent_ruff_table_is_one_missing_line_per_required_leaf(tmp_path: Path) -> None:
    """An absent `[tool.ruff]` reports each required leaf as missing.

    Args:
        tmp_path: A fresh temporary directory.
    """
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", pyproject(ruff=False)))
    assert (status, out) == (1, [])
    assert len(err) == 3, err
    assert err[0] == "pyproject.toml: [tool.ruff] line-length: missing, expected 120"
    assert err[1].startswith("pyproject.toml: [tool.ruff.lint] select: missing, expected "), err
    assert err[2].startswith("pyproject.toml: [tool.ruff.lint.pydocstyle] convention: missing, expected "), err


def test_several_violations_are_one_line_each_in_the_fixed_order(tmp_path: Path) -> None:
    """Several violations print one line each, in the fixed order.

    Args:
        tmp_path: A fresh temporary directory.
    """
    text = pyproject(
        line_length=100,
        convention="numpy",
        requires=">=3.11",
        tail="[tool.ty]\n\n[tool.interrogate]\n",
    )
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", text))
    assert (status, out) == (1, [])
    assert err[:3] == [
        'pyproject.toml: [project] requires-python: lower bound must be >= 3.12, found ">=3.11"',
        "pyproject.toml: [tool.ruff] line-length: expected 120, found 100",
        'pyproject.toml: [tool.ruff.lint.pydocstyle] convention: expected "google", found "numpy"',
    ]
    assert sorted(err[3:]) == [
        "pyproject.toml: [tool.interrogate] must be absent",
        "pyproject.toml: [tool.ty] must be absent",
    ]


def test_unparseable_pyproject_is_one_line(tmp_path: Path) -> None:
    """An unparseable pyproject.toml is one line.

    Args:
        tmp_path: A fresh temporary directory.
    """
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", "[project\nname = \n"))
    assert (status, out) == (1, [])
    assert len(err) == 1
    assert err[0].startswith("pyproject.toml: not valid TOML: "), err


def test_tracked_python_without_a_root_pyproject_fails(tmp_path: Path) -> None:
    """Tracked Python without a root pyproject.toml fails.

    Args:
        tmp_path: A fresh temporary directory.
    """
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", None))
    assert (status, out, err) == (
        1,
        [],
        ["pyproject.toml: missing at the repository root, but 1 tracked .py file(s)"],
    )


def test_a_pyproject_below_the_root_is_not_the_root_pyproject(tmp_path: Path) -> None:
    """A pyproject.toml below the root does not stand in for the root one.

    Args:
        tmp_path: A fresh temporary directory.
    """
    repo = floor_repo.make_repo(tmp_path / "repo", None, tracked_py=("pkg/module.py", "pkg/other.py"))
    (repo / "pkg" / "pyproject.toml").write_text(pyproject(ruff=False))
    floor_repo.git(repo, "add", "pkg/pyproject.toml")
    status, out, err = _run(repo)
    assert (status, out, err) == (
        1,
        [],
        ["pyproject.toml: missing at the repository root, but 2 tracked .py file(s)"],
    )


def test_no_tracked_python_passes_with_the_no_python_line(tmp_path: Path) -> None:
    """A repository with no tracked Python passes with the no-Python line.

    Args:
        tmp_path: A fresh temporary directory.
    """
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", None, tracked_py=()))
    assert (status, out, err) == (0, [NO_PYTHON_LINE], [])


def test_untracked_python_is_not_python(tmp_path: Path) -> None:
    """An untracked `.py` file is not Python.

    Args:
        tmp_path: A fresh temporary directory.
    """
    repo = floor_repo.make_repo(tmp_path / "repo", None, tracked_py=(), untracked_py=("loose.py",))
    status, out, err = _run(repo)
    assert (status, out, err) == (0, [NO_PYTHON_LINE], [])


def test_without_tracked_python_the_pyproject_is_not_read(tmp_path: Path) -> None:
    """Without tracked Python the pyproject.toml is not read.

    Args:
        tmp_path: A fresh temporary directory.
    """
    repo = floor_repo.make_repo(tmp_path / "repo", pyproject(line_length=100, tail="[tool.ty]\n"), tracked_py=())
    status, out, err = _run(repo)
    assert (status, out, err) == (0, [NO_PYTHON_LINE], [])


def test_the_readme_states_the_floor_values() -> None:
    """The README carries every value the module enforces, so a constant cannot change unseen."""
    readme = (Path(check_python_floor.__file__).parents[1] / "README.md").read_text()
    for value in (
        f"line-length = {check_python_floor.LINE_LENGTH}",
        ", ".join(check_python_floor.SELECT),
        f'"{check_python_floor.CONVENTION}"',
        ".".join(map(str, check_python_floor.MIN_PYTHON)),
    ):
        assert value in readme, value


STRAY_FILES = {
    "ruff.toml": 'lint.ignore = ["ALL"]\n',
    ".ruff.toml": "line-length = 88\n",
    "ty.toml": '[rules]\ninvalid-explicit-return = "ignore"\n',
    "sub/ruff.toml": 'format.exclude = ["*"]\n',
    "sub/ty.toml": "[rules]\n",
}


@pytest.mark.parametrize("path", STRAY_FILES, ids=STRAY_FILES.keys())
def test_a_tracked_side_configuration_file_is_one_violation(tmp_path: Path, path: str) -> None:
    """A tracked ruff or ty configuration file, at any depth, fails the floor on its own line.

    Args:
        tmp_path: A fresh temporary directory.
        path: The configuration file's tracked path.
    """
    repo = floor_repo.make_repo(tmp_path / "repo", pyproject(), extra_files={path: STRAY_FILES[path]})
    status, out, err = _run(repo)
    assert (status, out, err) == (1, [], [f"{path}: not allowed by the floor"])


def test_side_configuration_cannot_bypass_an_otherwise_passing_floor(tmp_path: Path) -> None:
    """A conformant root pyproject.toml plus a ruff.toml ignoring every rule and a ty.toml ignoring a rule fails.

    Args:
        tmp_path: A fresh temporary directory.
    """
    extra = {"ruff.toml": STRAY_FILES["ruff.toml"], "ty.toml": STRAY_FILES["ty.toml"]}
    status, out, err = _run(floor_repo.make_repo(tmp_path / "repo", pyproject(), extra_files=extra))
    assert (status, out) == (1, [])
    assert err == ["ruff.toml: not allowed by the floor", "ty.toml: not allowed by the floor"]


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("[tool.ruff]\nline-length = 88\n", ["sub/pyproject.toml: [tool.ruff] not allowed by the floor"]),
        ("[tool.ty.rules]\n", ["sub/pyproject.toml: [tool.ty] not allowed by the floor"]),
        (
            "[tool.ruff]\n[tool.ty]\n",
            [
                "sub/pyproject.toml: [tool.ruff] not allowed by the floor",
                "sub/pyproject.toml: [tool.ty] not allowed by the floor",
            ],
        ),
        ("[tool.pytest.ini_options]\naddopts = []\n", []),
        ("[project\n", ["sub/pyproject.toml: not valid TOML: "]),
    ],
    ids=["ruff", "ty", "both", "other tools are not the floor's concern", "unparseable"],
)
def test_a_non_root_pyproject_may_not_configure_ruff_or_ty(tmp_path: Path, text: str, lines: list[str]) -> None:
    """A pyproject.toml below the root fails on `[tool.ruff]` or `[tool.ty]` and on invalid TOML, and only then.

    Args:
        tmp_path: A fresh temporary directory.
        text: The nested pyproject.toml text.
        lines: The expected stderr lines, each a prefix of the real line.
    """
    repo = floor_repo.make_repo(tmp_path / "repo", pyproject(), extra_files={"sub/pyproject.toml": text})
    status, out, err = _run(repo)
    if not lines:
        assert (status, out, err) == (0, [PASS_LINE], [])
        return
    assert (status, out) == (1, [])
    assert len(err) == len(lines), err
    assert all(line.startswith(prefix) for line, prefix in zip(err, lines, strict=True)), err
