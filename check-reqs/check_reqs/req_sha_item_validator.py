"""Fails Doorstop's own validation when a referenced file has changed since the item reviewed it.

Compares each `references` entry's recorded `sha` against a fresh hash of the file at its `path`;
an entry with no recorded `sha` is skipped.
"""

from doorstop.common import DoorstopError


def item_validator(item):
    for reference in item.references or []:
        recorded = reference.get("sha")
        if recorded is not None and recorded != item._hash_reference(reference["path"]):
            yield DoorstopError(
                "referenced file changed since review: {}".format(reference["path"])
            )
