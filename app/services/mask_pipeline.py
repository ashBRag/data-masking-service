"""MaskPipelineService: orchestrates the mask-and-upload flow for one document.

document_url + masking_policy_id
  -> mint a fresh document id (nothing to look one up against here - no
     document table, just a mask-and-return-a-link job)
  -> look up the MaskingPolicy (must exist and be active)
  -> fetch the XML from document_url (SSRF-guarded, size/timeout bounded)
  -> MaskingService.mask()          - tokenize sensitive fields
  -> TokenPersistenceService.persist() - save the reversible token map
     (mask_tokens is the only thing persisted; MaskToken.document_id scopes
     those rows, it isn't a foreign key to a document table this service owns)
  -> S3Client.upload_bytes()        - upload the masked XML
  -> S3Client.presigned_url()       - hand back a time-limited download link

Keeps HTTP/S3/DB orchestration out of the route handler - the route only
translates this service's result to/from the API schema.
"""

from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.masking_policy import MaskingPolicy
from app.schemas.masking import MaskDocumentResponse
from app.services.masking import MaskingService, TokenPersistenceService
from libs.db import uuid7
from libs.errors import BadRequestError, NotFoundError
from libs.utils.http_fetch import FetchFailedError, InvalidUrlError, ResponseTooLargeError, fetch_url


class _Logger(Protocol):
    """Structural type for whatever logger MaskPipelineService is given."""

    def info(self, event: str, **kwargs: Any) -> None: ...


class _S3Client(Protocol):
    """Structural type for the subset of S3Client this service uses."""

    async def upload_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    async def presigned_url(self, key: str, expires_in: int = 3600) -> str: ...


class MaskPipelineService:
    """Runs the full mask -> persist -> upload pipeline for one document."""

    def __init__(
        self,
        session: AsyncSession,
        s3: _S3Client,
        *,
        allowed_fetch_schemes: list[str],
        fetch_max_bytes: int,
        fetch_timeout_seconds: float,
        presigned_url_expiry_seconds: int,
        logger: _Logger | None = None,
    ):
        """Store collaborators and the fetch/upload bounds this pipeline enforces."""
        self._session = session
        self._s3 = s3
        self._allowed_fetch_schemes = allowed_fetch_schemes
        self._fetch_max_bytes = fetch_max_bytes
        self._fetch_timeout_seconds = fetch_timeout_seconds
        self._presigned_url_expiry_seconds = presigned_url_expiry_seconds
        self._logger = logger
        self._masking_service = MaskingService(logger=logger)
        self._token_persistence_service = TokenPersistenceService(session, logger=logger)

    async def _get_active_policy(self, masking_policy_id: UUID) -> MaskingPolicy:
        """Look up a MaskingPolicy by id, requiring it to exist and be active."""
        policy = await self._session.get(MaskingPolicy, masking_policy_id)
        if policy is None:
            raise NotFoundError(f"Masking policy {masking_policy_id} not found")
        if not policy.is_active:
            raise BadRequestError(f"Masking policy {masking_policy_id} is not active")
        return policy

    def _masked_object_key(self, document_id: UUID) -> str:
        """S3 key the masked document for `document_id` is uploaded to.

        Fixed per document_id (not versioned/unique per run) - re-masking
        the same document overwrites its previous masked file.
        """
        return f"masked/{document_id}.xml"

    async def run(self, document_url: str, masking_policy_id: UUID) -> MaskDocumentResponse:
        """Fetch, mask, persist tokens for, and upload one document.

        Mints a fresh document id for this run (there's no document table
        to receive one from) and returns it, so the caller has a handle for
        looking up the masked file / mask_tokens rows later.

        Args:
            document_url: HTTPS URL the source XML is fetched from.
            masking_policy_id: Id of the (must be active) MaskingPolicy to apply.

        Raises:
            NotFoundError: `masking_policy_id` doesn't match an existing policy.
            BadRequestError: The policy is inactive, `document_url` fails SSRF/
                scheme validation, or the fetched document exceeds the size limit.

        Returns:
            MaskDocumentResponse: The minted document id, masking stats, and
            a presigned URL to the masked file.
        """
        document_id = uuid7()
        policy = await self._get_active_policy(masking_policy_id)

        try:
            fetched = await fetch_url(
                document_url,
                allowed_schemes=self._allowed_fetch_schemes,
                max_bytes=self._fetch_max_bytes,
                timeout_seconds=self._fetch_timeout_seconds,
            )
        except InvalidUrlError as exc:
            raise BadRequestError(f"Invalid document_url: {exc}") from exc
        except ResponseTooLargeError as exc:
            raise BadRequestError(str(exc)) from exc
        except FetchFailedError as exc:
            raise BadRequestError(f"Could not fetch document_url: {exc}") from exc

        result = self._masking_service.mask(fetched.content, policy, str(document_id))

        tokens_persisted = await self._token_persistence_service.persist(result)
        await self._session.commit()

        object_key = self._masked_object_key(document_id)
        await self._s3.upload_bytes(object_key, result.masked_xml, content_type="application/xml")
        masked_file_url = await self._s3.presigned_url(object_key, expires_in=self._presigned_url_expiry_seconds)

        if self._logger is not None:
            self._logger.info(
                "document_mask_pipeline_completed",
                document_id=str(document_id),
                masking_policy_id=str(masking_policy_id),
                fields_masked=result.fields_masked,
                tokens_generated=result.tokens_generated,
                tokens_persisted=tokens_persisted,
            )

        return MaskDocumentResponse(
            document_id=document_id,
            masking_policy_id=masking_policy_id,
            masked_file_url=masked_file_url,
            fields_masked=result.fields_masked,
            tokens_generated=result.tokens_generated,
            tokens_persisted=tokens_persisted,
        )
