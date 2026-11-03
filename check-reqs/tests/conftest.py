"""Builds check-reqs' starting Doorstop tree once per pytest session (per xdist worker), with the
real `doorstop` CLI, and copies it into each case's own directory. Cases share nothing: a case
that mutates its copy never affects another case's copy or the session's own baseline.
"""

import shutil
from pathlib import Path

import pytest

import minimal_tree


@pytest.fixture(scope="session")
def baseline_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = minimal_tree.init_repo(tmp_path_factory.mktemp("baseline"))
    minimal_tree.build(directory)
    return directory


@pytest.fixture
def repo(baseline_tree: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "repo"
    shutil.copytree(baseline_tree, destination, symlinks=True)
    return destination
