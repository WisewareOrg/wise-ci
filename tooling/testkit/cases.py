"""testkit.cases.Case / case_id (plan #4 W2, decision 10; owner, 2026-09-28: no origin field)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    slug: str
    row: str
    direction: str


def case_id(case: Case) -> str:
    return f"{case.direction}-{case.slug}"
