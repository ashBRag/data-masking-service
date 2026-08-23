"""Structure-preserving XML masking: replace sensitive element text with tokens.

Generic and reusable: takes the set of element paths to mask and a token
generator function, so it has no dependency on any particular policy model
or tokenization scheme - callers decide what "sensitive" and "token" mean.

Uses defusedxml's parser (XXE-safe) and Python's stdlib ElementTree
serializer, so it's safe on untrusted XML and needs no extra dependency
beyond what libs.utils.xml_parser already pulls in.

Usage:

    from libs.utils.xml_masking import mask_xml
    from libs.utils.tokeniser import tokenize

    masked_bytes, token_map = mask_xml(
        xml,
        fields={"Activity/Name", "Id"},
        make_token=lambda value, field: tokenize(value, field),
    )
    # token_map: {token: (original_value, field_type)}
"""

from collections.abc import Callable
from io import BytesIO
from xml.etree.ElementTree import tostring  # noqa: S405 - only used to serialize; parsing goes through defusedxml

from defusedxml.ElementTree import parse

TokenFactory = Callable[[str, str], str]


def _local_name(tag: str) -> str:
    """Strip a "{namespace-uri}" prefix off an ElementTree tag, if present."""
    return tag.rpartition("}")[2] if "}" in tag else tag


def mask_xml(xml: bytes, fields: set[str], make_token: TokenFactory) -> tuple[bytes, dict[str, tuple[str, str]]]:
    """Replace the text of every element matching an entry in `fields`.

    Each entry in `fields` is either a bare local tag name (e.g. `"Id"`,
    matching that tag under any parent) or a `"Parent/Tag"` path (e.g.
    `"Activity/Name"`, matching that tag only when its immediate parent's
    local tag is `Parent`). Namespace prefixes are ignored on both sides.
    Use a path when the same tag name is reused under multiple parents with
    different sensitivity (e.g. `Activity/Name` is a task title,
    `Resource/Name` is a person's name, `Calendar/Name` is neither) - a bare
    tag name matches that tag everywhere, which over-masks in documents like
    Primavera P6/MS Project XML where structural tags (`ObjectId`, `GUID`,
    `SequenceNumber`) and `Name` repeat once per row across many element
    types.

    Only element *text* is replaced (e.g. `<Name>Alice</Name>` ->
    `<Name>{token}</Name>`); element tags, attributes, and document
    structure are left untouched. Elements with no text, or whose text is
    only whitespace, are left as-is (nothing sensitive to mask).

    Args:
        xml: The raw XML document to mask.
        fields: Local element tag names, or "ParentTag/ChildTag" paths
            (namespace prefixes ignored), whose text content should be
            tokenized.
        make_token: Called as `make_token(original_text, field_tag)` for
            each matched element; its return value replaces the element's
            text. `field_tag` is always the bare child tag name, even when
            matched via a "Parent/Tag" path.

    Returns:
        tuple[bytes, dict[str, tuple[str, str]]]: The masked XML,
        re-serialized, and a map of `token -> (original_value, field_type)`
        for every element that was replaced - the caller needs this to
        persist a reversible token lookup; a duplicate original value for
        the same field type collapses to one entry (its token repeats).
    """
    tree = parse(BytesIO(xml))
    root = tree.getroot()

    bare_fields = {f for f in fields if "/" not in f}
    scoped_fields = {tuple(f.split("/", 1)) for f in fields if "/" in f}

    token_map: dict[str, tuple[str, str]] = {}
    parent_map = {child: parent for parent in root.iter() for child in parent}

    for element in root.iter():
        field_type = _local_name(element.tag)
        parent = parent_map.get(element)
        parent_name = _local_name(parent.tag) if parent is not None else None

        matches = field_type in bare_fields or (parent_name, field_type) in scoped_fields
        if not matches:
            continue
        if element.text is None or not element.text.strip():
            continue

        original_value = element.text
        token = make_token(original_value, field_type)
        token_map[token] = (original_value, field_type)
        element.text = token

    return tostring(root), token_map
