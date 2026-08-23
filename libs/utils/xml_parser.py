"""Streaming, namespace-aware XML parser (XXE-safe).

Generic and reusable

Built on defusedxml's iterparse (a drop-in, hardened wrapper around
xml.etree.ElementTree.iterparse) so external entity / DTD attacks are
rejected by default - safe to use on XML from an untrusted source.

Usage:

    from libs.utils.xml_parser import iter_elements

    # by local tag name, ignoring namespace
    for el in iter_elements("large-file.xml", tag="item"):
        print(el.text)

    # namespace-aware: pass a prefix map and refer to tags as "prefix:local"
    namespaces = {"ns": "http://example.com/schema"}
    for el in iter_elements("large-file.xml", tag="ns:item", namespaces=namespaces):
        print(el.attrib)

    # works with any file-like object too, not just paths
    with open("large-file.xml", "rb") as f:
        for el in iter_elements(f, tag="item"):
            ...
"""

from collections.abc import Iterable, Iterator
from typing import IO
from xml.etree.ElementTree import (
    Element,  # noqa: S405 - only used for type hints; parsing itself goes through defusedxml
)

from defusedxml.ElementTree import iterparse

XmlSource = str | IO[bytes] | IO[str]


def _resolve_tag(tag: str, namespaces: dict[str, str] | None) -> str:
    """Turn a "prefix:local" tag into ElementTree's "{namespace-uri}local" form.

    A bare tag (no ":") or one with no matching prefix in `namespaces` is
    returned unchanged, so callers can still match un-namespaced elements or
    match by local name only (see `_local_name`).
    """
    if namespaces and ":" in tag:
        prefix, _, local = tag.partition(":")
        if prefix in namespaces:
            return f"{{{namespaces[prefix]}}}{local}"
    return tag


def _local_name(tag: str) -> str:
    """Strip a "{namespace-uri}" prefix off an ElementTree tag, if present."""
    return tag.rpartition("}")[2] if "}" in tag else tag


def iter_elements(
    source: XmlSource,
    tag: str | Iterable[str] | None = None,
    namespaces: dict[str, str] | None = None,
) -> Iterator[Element]:
    """Stream-parse XML, yielding each completed element that matches `tag`.

    Args:
        source: A file path, or any file-like object opened for reading
            (binary or text) - passed straight through to iterparse.
        tag: Which element(s) to yield:
            - None: yield every element in the document.
            - A single tag: e.g. "item", or "ns:item" if `namespaces` is given.
            - An iterable of tags: yield elements matching any of them.
            Matching is namespace-aware when `namespaces` is provided
            (via the "prefix:local" form); otherwise it matches by local
            name only, ignoring whatever namespace the element is actually in.
        namespaces: Maps a short prefix to its full namespace URI, e.g.
            {"ns": "http://example.com/schema"}, so `tag` can use "ns:item"
            instead of the verbose "{http://example.com/schema}item" form.

    Yields:
        Element: each matching element, fully populated (all children/text/
        attributes present) at the moment it's yielded.

    Note:
        Elements are cleared (`element.clear()`) after being yielded to keep
        memory bounded on large documents - do not hold onto a yielded
        element expecting to read from it again after the next iteration.
    """
    if isinstance(tag, str):
        wanted_tags = {_resolve_tag(tag, namespaces)}
    elif tag is not None:
        wanted_tags = {_resolve_tag(t, namespaces) for t in tag}
    else:
        wanted_tags = None

    # Matching falls back to local-name-only comparison when the caller's
    # wanted tag has no namespace declared (no "{...}" from _resolve_tag) but
    # the document itself is namespaced - keeps `tag="item"` usable without
    # requiring the caller to know/declare every document's namespace URI.
    wanted_local_names = {_local_name(t) for t in wanted_tags} if wanted_tags else None

    for event, element in iterparse(source, events=("end",)):
        if event != "end":
            continue

        if wanted_tags is None or element.tag in wanted_tags or _local_name(element.tag) in wanted_local_names:
            yield element
            element.clear()
