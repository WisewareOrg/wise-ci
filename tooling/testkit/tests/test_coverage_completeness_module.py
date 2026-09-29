"""Confirms testkit.guards.coverage_completeness is safely importable as a plain module — the
`if __name__ == "__main__":` guard's other arm, which the CLI-invocation tests
(test_coverage_completeness_guard.py, subprocess-only) never exercise.
"""

import testkit.guards.coverage_completeness as coverage_completeness


def test_module_is_importable_without_running_main():
    assert callable(coverage_completeness.main)
