"""Applies a MaskingPolicy to XML, producing the masked XML and its token -> original-value map.

Security requirement: original (unmasked) field values must never be
logged. Log statements in this module only ever carry counts and ids -
never a value drawn from element text or MaskingResult.token_map.
"""

from typing import Any, Protocol

from app.models.masking_policy import MaskingPolicy
from app.schemas.masking import MaskingResult
from libs.utils.tokeniser import tokenize
from libs.utils.xml_masking import mask_xml


class _Logger(Protocol):
    """Structural type for whatever logger MaskingService is given."""

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
