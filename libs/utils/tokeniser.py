"""Deterministic tokenization for masking sensitive field values.

Pure and dependency-light: no framework or settings dependency - safe to
reuse anywhere a sensitive value needs to be replaced with a stable,
non-reversible token before storage or logging.

Uses SHA-256 (not Python's built-in `hash()`, which is randomized per
process via `PYTHONHASHSEED` and not stable across runs) so the same
field type + value always produces the same token, both within a single
file and across separate processes/runs.

Usage:

    from libs.utils.tokeniser import tokenize

    tokenize("Alice", "Name")   # -> "<TOKEN_NAME_9a1c3f2b8e7d4a6f>"
    tokenize("Alice", "Name")   # -> same token, every time
    tokenize("Bob", "Name")     # -> a different token
"""

import hashlib

TOKEN_FORMAT = "<TOKEN_{type}_{hash}>"
HASH_LENGTH = 16


def tokenize(value: str, field_type: str) -> str:
    """Deterministically map a sensitive value to a stable, opaque token.

    The same (field_type, value) pair always yields the same token; a
    different value (for the same or a different field_type) yields a
    different token. The original value is never recoverable from the
    token - it's a one-way SHA-256 digest, not an encoding of the value.

    Args:
        value: The sensitive value to tokenize.
        field_type: The kind of field `value` came from (e.g. "Name",
            "Id"). Included in the hash input so the same raw value used
            for two different field types still tokenizes differently.

    Returns:
        str: A token of the form "<TOKEN_{FIELD_TYPE}_{hash}>".
    """
    digest = hashlib.sha256(f"{field_type}:{value}".encode()).hexdigest()[:HASH_LENGTH]
    return TOKEN_FORMAT.format(type=field_type.upper(), hash=digest)
