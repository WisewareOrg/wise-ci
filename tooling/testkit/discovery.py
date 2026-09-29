"""testkit.discovery.check_dirs: the top-level directories that are checks (ADR 0001 rev 1 point 1:
a top-level folder holding an action.yml/action.yaml is a check).
"""

from pathlib import Path

_MANIFESTS = ("action.yml", "action.yaml")


def check_dirs(root: Path) -> list[Path]:
    return [
        entry
        for entry in sorted(root.iterdir())
        if entry.is_dir() and any((entry / manifest).exists() for manifest in _MANIFESTS)
    ]
