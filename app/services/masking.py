"""Applies a MaskingPolicy to XML, and persists the resulting token -> original-value map.

Security requirement: original (unmasked) field values must never be
logged. Log statements in this module only ever carry counts and ids -
never a value drawn from element text or MaskingResult.token_map.
"""

import uuid
from typing import Any, Protocol

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mask_token import MaskToken
from app.models.masking_policy import MaskingPolicy
from app.schemas.masking import MaskingResult
from libs.utils.tokeniser import tokenize
from libs.utils.xml_masking import mask_xml


class _Logger(Protocol):
    """Structural type for whatever logger MaskingService/TokenPersistenceService is given."""

    def info(self, event: str, **kwargs: Any) -> None: ...


class MaskingService:
    """Masks sensitive values in an XML document according to a MaskingPolicy."""

    def __init__(self, logger: _Logger | None = None):
        """Store an optional logger; a no-op if none is given."""
        self._logger = logger

    def mask(
        self,
        xml: bytes,
        policy: MaskingPolicy,
        document_id: str,
    ) -> MaskingResult:
        """Mask every field in `policy.fields` within `xml`, returning the result.

        Args:
            xml: The raw XML document to mask.
            policy: Which fields to mask and how (`policy.fields` names the
                elements; `policy.token_format` controls the token shape via
                `libs.utils.tokeniser.tokenize`).
            document_id: Identifier of the source document, used only for
                logging/stats attribution - never echoed with a value.

        Returns:
            MaskingResult: The masked XML plus counts of fields masked and
            tokens generated.
        """
        fields = set(policy.fields)

        masked_xml, token_map = mask_xml(xml, fields=fields, make_token=tokenize)

        result = MaskingResult(
            document_id=document_id,
            masked_xml=masked_xml,
            fields_masked=len(token_map),
            tokens_generated=len(token_map),
            token_map=token_map,
        )

        if self._logger is not None:
            self._logger.info(
                "document_masked",
                document_id=document_id,
                policy_name=policy.policy_name,
                fields_masked=result.fields_masked,
                tokens_generated=result.tokens_generated,
            )

        return result


class TokenPersistenceService:
    """Persists a MaskingResult's token map as MaskToken rows for reversible lookup.

    original_value is currently stored as plain text (see MaskToken) - no
    encryption yet.
    """

    # Postgres caps a single query at 65535 bound parameters. Each MaskToken
    # row binds 6 columns (id, document_id, token, token_type,
    # original_value, created_at - the latter filled client-side by
    # TimestampedModel's default_factory), so this leaves ample headroom
    # below the 65535/6 = 10922 row ceiling.
    _BATCH_SIZE = 5000

    def __init__(self, session: AsyncSession, logger: _Logger | None = None):
        """Store the session used to write MaskToken rows, and an optional logger."""
        self._session = session
        self._logger = logger

    async def persist(self, result: MaskingResult) -> int:
        """Upsert one MaskToken row per entry in `result.token_map`, keyed on (document_id, token).

        Upsert (not plain insert) so re-running ingestion for the same
        document - e.g. a retry after a later pipeline step failed - is
        idempotent instead of hitting mask_tokens' UNIQUE(document_id, token)
        constraint. Does not commit - the caller controls the transaction
        boundary (e.g. committing alongside the rest of the document-ingestion write).

        Args:
            result: The MaskingResult to persist tokens for.

        Returns:
            int: The number of MaskToken rows upserted.
        """
        if not result.token_map:
            return 0

        document_id = uuid.UUID(result.document_id)
        rows = [
            {
                "id": uuid.uuid4(),
                "document_id": document_id,
                "token": token,
                "token_type": field_type,
                "original_value": original_value,
            }
            for token, (original_value, field_type) in result.token_map.items()
        ]

        for batch in (rows[i : i + self._BATCH_SIZE] for i in range(0, len(rows), self._BATCH_SIZE)):
            stmt = insert(MaskToken.__table__).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["document_id", "token"],
                set_={
                    "token_type": stmt.excluded.token_type,
                    "original_value": stmt.excluded.original_value,
                },
            )
            await self._session.execute(stmt)

        if self._logger is not None:
            self._logger.info(
                "tokens_persisted",
                document_id=result.document_id,
                tokens_persisted=len(result.token_map),
            )

        return len(result.token_map)
