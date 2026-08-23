"""Result shape returned by MaskingService.mask(), plus the POST /mask API schemas."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class MaskingResult:
    """The output of masking one document: the masked XML, stats, and the token map.

    `token_map` (token -> (original_value, field_type)) carries the
    original values needed to persist a reversible lookup - it exists to be
    read by TokenPersistenceService, not to be logged. Never log this field.
    """

    document_id: str
    masked_xml: bytes
    fields_masked: int
    tokens_generated: int
    token_map: dict[str, tuple[str, str]]


class MaskDocumentRequest(BaseModel):
    """POST /api/v1/mask request body.

    No document_id: this service has no document table to look one up
    against, so it mints one itself (see MaskPipelineService.run) and hands
    it back in the response.
    """

    document_url: str = Field(
        min_length=1,
        max_length=2048,
        description="HTTPS URL the source XML document is fetched from.",
    )
    masking_policy_id: UUID = Field(description="Id of the MaskingPolicy to apply.")


class MaskDocumentResponse(BaseModel):
    """POST /api/v1/mask response body."""

    document_id: UUID = Field(description="Id minted for this document; scopes the persisted MaskToken rows.")
    masking_policy_id: UUID
    masked_file_url: str = Field(description="Presigned URL the masked document was uploaded to.")
    fields_masked: int
    tokens_generated: int
    tokens_persisted: int
