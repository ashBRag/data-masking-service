"""Import every table model here so they all register on SQLModel's shared metadata.

Anything that needs to create tables / run migrations against the full
schema should `import app.models.database` (or import this module's
`__all__` members) rather than importing individual model files piecemeal.
"""

from app.models.mask_token import MaskToken
from app.models.masking_policy import MaskingPolicy

__all__ = [
    "MaskToken",
    "MaskingPolicy",
]
