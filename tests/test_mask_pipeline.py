"""Tests for MaskPipelineService's orchestration (policy lookup, fetch, mask, upload, no persistence)."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.models.masking_policy import MaskingPolicy
from app.services.mask_pipeline import MaskPipelineService
from libs.errors import BadRequestError, NotFoundError
from libs.utils.http_fetch import FetchedDocument

SAMPLE_XML = b"<Project><Resource><Name>Alice</Name></Resource></Project>"


def _make_policy(is_active: bool = True) -> MaskingPolicy:
    return MaskingPolicy(
        id=uuid4(),
        policy_name="test-policy",
        action="tokenize",
        strategy="deterministic",
        fields=["Resource/Name"],
        token_format="<TOKEN_{type}_{hash}>",
        rules={},
        is_active=is_active,
    )


def _make_service(session: AsyncMock, s3: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> MaskPipelineService:
    return MaskPipelineService(
        session,
        s3,
        allowed_fetch_schemes=["https"],
        fetch_max_bytes=1_000_000,
        fetch_timeout_seconds=5.0,
        presigned_url_expiry_seconds=3600,
    )


async def test_run_raises_not_found_for_missing_policy(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.get.return_value = None
    s3 = AsyncMock()
    service = _make_service(session, s3, monkeypatch)

    with pytest.raises(NotFoundError):
        await service.run("https://example.com/file.xml", uuid4())


async def test_run_raises_bad_request_for_inactive_policy(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.get.return_value = _make_policy(is_active=False)
    s3 = AsyncMock()
    service = _make_service(session, s3, monkeypatch)

    with pytest.raises(BadRequestError):
        await service.run("https://example.com/file.xml", uuid4())


async def test_run_generates_a_document_id_masks_uploads_and_returns_presigned_url(monkeypatch: pytest.MonkeyPatch):
    policy = _make_policy()
    session = AsyncMock()
    session.get.return_value = policy
    s3 = AsyncMock()

    def _fake_presigned_url(key: str, expires_in: int) -> str:
        return f"https://s3.example.com/{key}?sig=abc"

    s3.presigned_url.side_effect = _fake_presigned_url

    monkeypatch.setattr(
        "app.services.mask_pipeline.fetch_url",
        AsyncMock(return_value=FetchedDocument(content=SAMPLE_XML, content_type="application/xml")),
    )

    service = _make_service(session, s3, monkeypatch)
    response = await service.run("https://example.com/file.xml", policy.id)

    # No document_id is passed in - the service must generate its own.
    assert isinstance(response.document_id, UUID)
    expected_key = f"masked/{response.document_id}.xml"

    assert response.masking_policy_id == policy.id
    assert response.masked_file_url == f"https://s3.example.com/{expected_key}?sig=abc"
    assert response.fields_masked == 1
    assert response.tokens_generated == 1

    assert len(response.tokens) == 1
    entry = response.tokens[0]
    assert entry.field_type == "Name"
    assert entry.original_value == "Alice"

    s3.upload_bytes.assert_awaited_once()
    upload_key, upload_body = s3.upload_bytes.call_args.args[0], s3.upload_bytes.call_args.args[1]
    assert upload_key == expected_key
    assert b"Alice" not in upload_body

    s3.presigned_url.assert_awaited_once_with(expected_key, expires_in=3600)
    # Nothing is persisted server-side anymore - the pipeline never commits.
    session.commit.assert_not_awaited()


async def test_run_generates_a_different_document_id_each_call(monkeypatch: pytest.MonkeyPatch):
    policy = _make_policy()
    session = AsyncMock()
    session.get.return_value = policy
    s3 = AsyncMock()
    s3.presigned_url.return_value = "https://s3.example.com/masked.xml"

    monkeypatch.setattr(
        "app.services.mask_pipeline.fetch_url",
        AsyncMock(return_value=FetchedDocument(content=SAMPLE_XML, content_type="application/xml")),
    )

    service = _make_service(session, s3, monkeypatch)
    first = await service.run("https://example.com/file.xml", policy.id)
    second = await service.run("https://example.com/file.xml", policy.id)

    assert first.document_id != second.document_id


async def test_run_rejects_invalid_document_url(monkeypatch: pytest.MonkeyPatch):
    policy = _make_policy()
    session = AsyncMock()
    session.get.return_value = policy
    s3 = AsyncMock()
    service = _make_service(session, s3, monkeypatch)

    with pytest.raises(BadRequestError):
        await service.run("http://example.com/file.xml", policy.id)  # not https
