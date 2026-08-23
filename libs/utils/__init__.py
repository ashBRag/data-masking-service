"""Small, generic, dependency-light helpers that don't warrant their own package.

Self-contained: no dependency on any other libs/* package.
"""

from libs.utils.http_fetch import FetchedDocument, fetch_url
from libs.utils.tokeniser import tokenize
from libs.utils.xml_masking import mask_xml

__all__ = [
    "FetchedDocument",
    "fetch_url",
    "mask_xml",
    "tokenize",
]
