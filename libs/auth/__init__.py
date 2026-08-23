"""JWT verification helper.

Self-contained: no dependency on any other libs/* package.
"""

from libs.auth.base import verify_token

__all__ = ["verify_token"]
