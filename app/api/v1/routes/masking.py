"""POST /api/v1/mask: mask a document's sensitive fields and upload the result to S3."""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import MaskPipelineServiceDep, require_scopes
from app.core.config import settings
from app.core.limiter import limiter
from app.schemas.masking import MaskDocumentRequest, MaskDocumentResponse

router = APIRouter(tags=["masking"])


@router.post(
    "/mask",
    response_model=MaskDocumentResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_scopes())],
)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["mask"][0])
async def mask_document(
    request: Request,
    body: MaskDocumentRequest,
    pipeline: MaskPipelineServiceDep,
) -> MaskDocumentResponse:
    """Fetch `document_url`, mask it per `masking_policy_id`, and upload the result.

    Steps: generate a document id -> look up the masking policy (must exist and
    be active) -> fetch the XML from `document_url` (HTTPS only,
    SSRF-guarded, size/timeout bounded) -> mask sensitive fields -> persist
    the reversible token map -> upload the masked XML to S3 -> return a
    presigned download URL.
    """
    return await pipeline.run(
        document_url=body.document_url,
        masking_policy_id=body.masking_policy_id,
    )
