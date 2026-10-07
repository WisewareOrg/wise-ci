# check-reqs

Gates a [Doorstop](https://doorstop.readthedocs.io/) requirements tree shaped as three documents —
`sys`, `srs`, `tst` — each `SYS`/`SRS`/`TST` item one YAML file. It is the one shared implementation
of the gate WiseKiosk and meta-wisekiosk both run over their own trees.

## Inputs

See [`action.yml`](action.yml) for `root`'s description and default. The action requires `uv` on
`PATH`; it exists for wise-ci's own self-check and convention — a consumer installs the
distribution instead (see [Consuming check-reqs](#consuming-check-reqs) below).

## Stages, in order

Seven stages run in a fixed order and stop at the first that fails, each preceded by its own
`check-reqs: <stage>` header. `--root` is the directory holding `sys`/`srs`/`tst`; the Doorstop
project root is always the working directory (see [The `root` input](#the-root-input-and-the-project-root) below).

### `check_unreviewed`

Runs first because Doorstop writes. The first time it validates a tree, Doorstop stamps a review
fingerprint into any item whose `reviewed` value is absent, and into any link carrying no stamp —
whether or not a person looked, and `--no-reformat` does not stop it. An item authored in one commit
would otherwise read as reviewed by whoever next ran the gate, which is the one thing the
fingerprint exists to prove. This stage fails first and stops the gate before Doorstop's own
validation can stamp anything. `reviewed: true` is the same defect declared by hand: Doorstop reads
it as "matching, hash to follow" and fills the hash in unprompted the next time it validates. Clear
either by reading the item against its parent and running `doorstop review <uid>`, deliberately,
never by re-running the gate.

A link counts as unreviewed when its own stamp is absent, or when the item holding it is: a stamp is
a digest of the parent's content, so nothing reading the tree tells a copied one from an earned one.
Every document under `root` is checked — found by walking for `.doorstop.yml` — and each must yield
at least one item; a tier that yields nothing produces no finding, which reads exactly like a tier
whose every item is reviewed.

### `check_suspect_links`

Doorstop flags a link suspect when the parent's fingerprint no longer matches the stamp the child
was reviewed against — but it skips inactive items entirely, and every `TST` item in a
decomposition-pending tree sits inactive until its verification exists. This stage restores the
comparison for the items Doorstop's own validation skips, inactive items included, and also reports
an inactive link naming a parent no document holds. An active item's own suspect link is
`doorstop --error-all`'s to report; a link carrying no stamp at all is `check_unreviewed`'s, which
runs first.

### `doorstop --error-all --no-reformat`

Doorstop's own validation: every `SYS` need has a child `SRS`, every `SRS` has a child `TST`, no
`SRS`/`TST` is orphaned, and — through the `tst` document's `item_validator` extension
([`req_sha_item_validator.py`](check_reqs/req_sha_item_validator.py)) — every active `TST` item's
`references` resolve and no referenced file has changed since the item was reviewed. `--error-all`
promotes Doorstop's own suspect/unreviewed/orphan/unresolved-reference warnings to errors, so the
run actually blocks; plain `doorstop` only warns. `--no-reformat` stops Doorstop rewriting item
files on a passing run — it does not stop it writing a missing stamp, which is why
`check_unreviewed` runs first.

### `check_method_consistency`

`verification-method` ranks by mechanical decidability: `test` > `analysis` > `inspection` >
`demonstration`. This is deliberately not the classical V&V rigor ordering, which would rank
`demonstration` above `inspection` — ranked that way, "move to the stronger method" would push an
item onto physical hardware or a wall clock instead of into continuous integration.

Two rules: an item sits at the most decidable method it honestly supports, and a parent's method
equals the least decidable method among its children — the parent's obligation is the conjunction of
theirs, so it can be no more decidable than the least. The two directions are not symmetric.
**Overstating** — a parent above its least-decidable child — claims a machine settles what one of
its own obligations leaves to a human, and is never excusable. **Understating** — a parent below
every child — is permitted only where the parent holds a residual obligation no child carries, and
only with a written `verification-justification` arguing why the residue exists; without one it is
treated the same as overstating. `verification-justification` is also required on every normative
item on its own: below `test` it states what blocks a mechanical check, and at `test` it states what
the check still leaves unproven — an item with no justification would otherwise satisfy the rule by
having nothing to argue. A `normative: false` item obliges nothing, so it is exempt from both rules
and carries an empty method and no justification.

An unrecognised `verification-method` — a typo, a capitalised token, or the attribute missing —
ranks nowhere in the decidability order, so it is reported directly rather than silently skipped by
the rank comparison, which would otherwise exempt the item from judgment while reporting the tree
consistent.

### `check_text_citations`

An item's `text` must be understandable without a lookup — ISO/IEC/IEEE 29148's *complete* and
*singular* characteristics. An identifier inside it defeats both: the reader cannot tell what is
required without fetching the item it names, and a renumber rewrites `links:` while leaving the
sentence pointing at whatever now occupies the number. `rationale` and `verification-justification`
explain the tree to someone reading it as a tree, so they may name items freely; only `text` is
scanned, case-insensitively, for an `SYS`/`SRS`/`TST` identifier.

### `check_headers`

Every item's header must be non-empty, drawn from an allowlist (`A-Z a-z 0-9` space `, . ' ( ) & :
; -`), and not a case-insensitive prefix of another item's header. The allowlist is deliberately a
list of characters to *admit* rather than to reject: a header carrying `|` would split a table and
one carrying `-->` would close an HTML comment, and a denylist fails open on whichever metacharacter
nobody thought of. Prefix-freeness is the reader's constraint rather than the checker's — two
headers that begin alike are told apart only by reading to the end of both.

### `report_proposed`

Prints the `proposed`-item backlog per tier and always exits 0 — this stage reports, it never gates.
Two refusals, both of the kind where a wrong answer would read as a clean one: every tier prints,
zero included, so a line that disappears at a zero count cannot be told from a report that never
ran; and a status outside `proposed` | `accepted` is listed rather than silently counted as
baselined, so a mis-spelled status cannot deflate the very count this exists to surface.

## What this gate proves, and what it leaves to the consumer

Together these stages assert that, under `root`:

- no item carries a review fingerprint nobody wrote;
- every document yields at least one item to check;
- every parent link resolves and no item is orphaned or left suspect, inactive items included;
- every active `TST` item's `references` resolve, and no referenced file has changed since the item
  was reviewed;
- every item carries a `verification-justification`;
- no item claims a verification method its own children do not support;
- no item's `text` names another item;
- every header is non-empty, within the permitted set, and prefix-free.

It does not prove that a referenced check itself passes — only that a `TST` item points at a real
file. A consumer's own gate runs the checks the tree references.

## Known gaps

- A quoted, non-empty `reviewed:` string spelling falsehood passes `check_unreviewed` — it tests only
  that the value is a non-empty string, not that it is a real digest. The same gap swallows a pasted
  stamp copied from a genuinely reviewed item onto another: both are correct-looking strings for
  their own content, invisible either way. A forged item still fails the next real validation on
  content mismatch.
- Malformed item YAML raises a traceback rather than a diagnostic; the run still exits non-zero, so
  it fails closed.
- A `TST` item's *own* fingerprint is checked for presence by `check_unreviewed`, never for
  correctness by anything that reaches inactive items: `doorstop --error-all` skips inactive items
  entirely, and `check_suspect_links` scopes itself to link staleness. A stale stamp on an inactive
  item's own text or attributes passes every stage here.
- `report_proposed` prints `0 of 0` for a tier with no items, and exits 0 — visible only through its
  own population figure, since `check_unreviewed` fails that state before `report_proposed` ever
  runs in the fixed order.
- A mis-spelled status is listed by `report_proposed` as outside the vocabulary; nothing here gates
  it, for any tier.

## The `root` input and the project root

`--root` resolves against the working directory (`Path.cwd() / root`); an absolute value is
accepted as given. The Doorstop project root is always the working directory, never `root` —
`references[].path` and `Item._hash_reference` resolve against it — so a consumer runs `check-reqs`
from its repository root, exactly as it would run bare `doorstop` there today.

## Consuming check-reqs

Add the distribution at a pinned commit, with the version as a comment (as any other dependency
pinned against this repository — see [`../README.md`](../README.md) § Consuming a check for the
convention this follows):

```sh
uv add --group dev "check-reqs @ git+https://github.com/WisewareOrg/wise-ci@<sha>#subdirectory=check-reqs" # vX.Y.Z
```

or the equivalent pip spelling in a requirements file. This check owns the Doorstop pin; a consumer
takes Doorstop from it and pins no second copy. Run it from the repository root, behind the
consumer's own `just check-reqs` recipe:

```sh
check-reqs --root docs/requirements
```

The `tst` document's `item_validator` extension stays a one-line shim at
`docs/requirements/tst/.req_sha_item_validator.py`, importing the shared hook:

```python
from check_reqs.req_sha_item_validator import item_validator
```

and the document's `.doorstop.yml` keeps both extensions:

```yaml
extensions:
  item_sha_required: true
  item_validator: .req_sha_item_validator.py
```
