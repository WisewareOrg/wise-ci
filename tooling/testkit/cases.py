"""testkit.cases.Case / case_id (owner, 2026-09-28: no origin field)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    slug: str
    row: str
    direction: str


def case_id(case: Case) -> str:
    return f"{case.direction}-{case.slug}"
