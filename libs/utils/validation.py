"""Small, generic string-length validation helpers.

Pure functions, no framework/domain dependency - reusable anywhere a
free-text input needs a non-empty/max-length check before use.
"""


def validate_text_length(value: str, max_length: int, field_name: str = "value") -> str:
    """Trim `value` and check it's non-empty and within `max_length`.

    Args:
        value: The text to validate.
        max_length: Maximum allowed length, checked against the trimmed text.
        field_name: Used in the error message to identify which field failed.

    Raises:
        ValueError: If the trimmed text is empty, or longer than `max_length`.

    Returns:
        str: The trimmed text.
    """
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{field_name} must not be empty")
    if len(trimmed) > max_length:
        raise ValueError(f"{field_name} exceeds the maximum length of {max_length} characters")
    return trimmed
