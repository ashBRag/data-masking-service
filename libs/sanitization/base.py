"""String/dict/list sanitization helpers to guard against XSS and injection.

Pure functions, no framework or settings dependency - safe to reuse anywhere
you need to clean untrusted input before storing or echoing it back.
"""

import html
import re
from typing import Any


def sanitize_string(value: str) -> str:
    """HTML-escape a value and strip null bytes / stray script tags.

    Args:
        value: The string to sanitize (non-strings are coerced via str()).

    Returns:
        str: The sanitized string.
    """
    if not isinstance(value, str):
        value = str(value)

    # Escape first so any legitimate "<" or "&" in user content becomes inert.
    value = html.escape(value)

    # Belt-and-braces: strip fully-escaped <script>...</script> blocks that survived escaping.
    value = re.sub(r"&lt;script.*?&gt;.*?&lt;/script&gt;", "", value, flags=re.DOTALL)

    # Null bytes break some downstream consumers (DB drivers, C string APIs).
    value = value.replace("\0", "")

    return value


def sanitize_email(email: str) -> str:
    """Sanitize and validate an email address, returning it lowercased.

    Args:
        email: The email address to sanitize.

    Raises:
        ValueError: If the value doesn't look like a valid email after sanitizing.

    Returns:
        str: The sanitized, lowercased email address.
    """
    email = sanitize_string(email)

    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValueError("Invalid email format")

    return email.lower()


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitize every string value in a dict (including nested dicts/lists).

    Args:
        data: The dictionary to sanitize.

    Returns:
        dict[str, Any]: A new dict with all string values sanitized.
    """
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = sanitize_list(value)
        else:
            sanitized[key] = value
    return sanitized


def sanitize_list(data: list[Any]) -> list[Any]:
    """Recursively sanitize every string value in a list (including nested dicts/lists).

    Args:
        data: The list to sanitize.

    Returns:
        list[Any]: A new list with all string values sanitized.
    """
    sanitized: list[Any] = []
    for item in data:
        if isinstance(item, str):
            sanitized.append(sanitize_string(item))
        elif isinstance(item, dict):
            sanitized.append(sanitize_dict(item))
        elif isinstance(item, list):
            sanitized.append(sanitize_list(item))
        else:
            sanitized.append(item)
    return sanitized
