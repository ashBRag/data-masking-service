"""Project-level alias for the shared SQLModel base.

Import BaseModel from here in this project's models so the reusable base
class lives in one place (libs/db/base.py) but call sites stay
project-idiomatic.
"""

from libs.db import TimestampedModel as BaseModel

__all__ = ["BaseModel"]
