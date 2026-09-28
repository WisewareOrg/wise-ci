---
name: Design decision (ADR)
about: Open a trade discussion that ends in an ADR
labels: design, documentation
---

An ADR captures a decision **with a rejected alternative** (`docs/decisions/README.md`).
This ticket is the entry point: the trades are walked conversationally and the owner decides — the
ADR transcribes the outcome, it never buries a choice nobody discussed. If there is no real
alternative to weigh, this doesn't need a ticket or an ADR.

**Decision to be made**

<!-- One sentence, phrased as the choice — "how do we X", not "we should X". -->

**What forces it**

<!-- The constraint, gap, or event that made "just pick something" not good enough. -->

**Options on the table**

<!-- Known candidates, one line each. Incomplete is fine; the discussion will grow it. -->

**Prior art implicated**

<!-- Existing ADRs, checks, or gates this touches or might supersede. -->

**Definition of done**

- [ ] Trades walked conversationally; owner decided each point (none resolved silently in a draft).
- [ ] ADR merged: numbered per `docs/decisions/TEMPLATE.md`, indexed in the README table, at least
      one real rejected alternative with the why.
- [ ] Anything left open is carried to the implementation ticket **explicitly marked open**.
- [ ] Implementation ticket created citing the ADR (or explicitly not needed).
- [ ] Operative docs untouched — they describe current behavior and change only when
      implementation lands.
