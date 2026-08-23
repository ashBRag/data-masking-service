"""The `mask_tokens` table: reversible mapping between a masked token and its original value."""

import uuid

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel
from libs.db import uuid7


class MaskToken(BaseModel, table=True):
    """One masked-value <-> original-value mapping, scoped to a document.

    original_value is stored as plain text for now (no encryption yet) -
    revisit before this holds anything sensitive in a non-dev environment.
    """

    __tablename__ = "mask_tokens"
    __table_args__ = (UniqueConstraint("document_id", "token"),)

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="documents.id", ondelete="CASCADE", index=True)
    token: str
    # No fixed set of values specified yet - kept as plain str; convert to a
    # StrEnum once the concrete token type categories are known.
    token_type: str
    original_value: str
