"""String/dict/list sanitization helpers against XSS and injection.

Self-contained: no dependency on any other libs/* package.
"""

from libs.sanitization.base import (
    sanitize_dict,
    sanitize_email,
    sanitize_list,
    sanitize_string,
)

__all__ = ["sanitize_dict", "sanitize_email", "sanitize_list", "sanitize_string"]
