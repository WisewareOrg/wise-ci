"""Confirms check-eol/check-eol.py is safely importable as a plain module -- the `if __name__ ==
"__main__":` guard's other arm, which test_cases.py can never exercise (decision 3: the script is
run as a subprocess from its real path, never imported).
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-eol.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_eol_module_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_is_importable_without_running_main():
    module = _load()
    assert callable(module.main)
