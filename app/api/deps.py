"""Shared FastAPI dependency providers for the API layer.

Builds request-scoped service instances (session-bound services) from the
app-wide singletons constructed in app/main.py (db, s3, logger).
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.mask_pipeline import MaskPipelineService
from libs.aws import S3Client


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped DB session from the app-wide Database instance."""
    from app.main import db

    async for session in db.get_session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_s3_client() -> S3Client:
    """Return the app-wide S3Client (S3-compatible: AWS, LocalStack, or Supabase Storage)."""
    from app.main import s3

    return s3


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]


def get_mask_pipeline_service(session: SessionDep, s3: S3ClientDep) -> MaskPipelineService:
    """Build a MaskPipelineService bound to the given request-scoped session."""
    from app.main import logger

    return MaskPipelineService(
        session,
        s3,
        allowed_fetch_schemes=settings.DOCUMENT_FETCH_ALLOWED_SCHEMES,
        fetch_max_bytes=settings.DOCUMENT_FETCH_MAX_BYTES,
        fetch_timeout_seconds=settings.DOCUMENT_FETCH_TIMEOUT_SECONDS,
        presigned_url_expiry_seconds=settings.S3_PRESIGNED_URL_EXPIRY_SECONDS,
        logger=logger,
    )


MaskPipelineServiceDep = Annotated[MaskPipelineService, Depends(get_mask_pipeline_service)]
