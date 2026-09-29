"""Shared git isolation (TESTING.md D5): no ambient host git config reaches a fixture repository
or a script run under test. Merged into the environment of every git invocation testkit makes on
a test's behalf.
"""

GIT_ISOLATION = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}
