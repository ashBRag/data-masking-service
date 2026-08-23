"""The `masking_policies` table: versioned configuration for how sensitive fields get tokenized."""

import uuid
from typing import Any

from sqlalchemy import Column
from sqlalchemy import String as SaString
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field

from app.models.base import BaseModel
from libs.db import uuid7


class MaskingPolicy(BaseModel, table=True):
    """One masking/tokenization policy configuration.

    Kept as a table (not a static config file) so new policies can be added
    or an existing one revised without a code deploy - query for
    `is_active=True` to get the policy currently in effect.
    """

    __tablename__ = "masking_policies"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    policy_name: str = Field(unique=True)
    action: str
    strategy: str
    fields: list[str] = Field(sa_column=Column(ARRAY(SaString)))
    token_format: str
    rules: dict[str, Any] = Field(sa_column=Column(JSONB))
    is_active: bool = Field(default=True, index=True)
