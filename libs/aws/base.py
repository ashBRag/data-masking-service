"""Reusable async AWS client: S3 only (aioboto3).

Generic and reusable: takes an `AwsSettings` value object instead of
importing any project's settings class, so it can be reused as-is in
another project.

Each call opens a fresh client from the shared aioboto3.Session as an async
context manager - this matches aioboto3's own recommended usage (clients
are cheap to create and not meant to be held open indefinitely), so there's
no connect()/disconnect() lifecycle here unlike libs/db.

Usage:

    from libs.aws import AwsSettings, S3Client

    aws_settings = AwsSettings(region_name=settings.AWS_REGION)
    s3 = S3Client(aws_settings, bucket=settings.S3_BUCKET)

    await s3.upload_bytes("path/to/key.json", b'{"a": 1}')
    data = await s3.download_bytes("path/to/key.json")
"""

from dataclasses import dataclass

import aioboto3


@dataclass(frozen=True)
class AwsSettings:
    """Credentials/region for AWS clients.

    A plain value object (not a pydantic BaseSettings) so libs/aws has zero
    dependency on any particular settings/config library - the caller reads
    these values from wherever it likes and passes them in.

    Leave access_key_id/secret_access_key as None to fall back to the
    default boto3 credential chain (env vars, instance profile, etc.) -
    the recommended approach outside of local dev.
    """

    region_name: str = "us-east-1"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    endpoint_url: str | None = None  # e.g. for LocalStack in local dev

    def session_kwargs(self) -> dict:
        """Build the kwargs shared by every aioboto3 client() call."""
        kwargs: dict = {"region_name": self.region_name}
        if self.access_key_id and self.secret_access_key:
            kwargs["aws_access_key_id"] = self.access_key_id
            kwargs["aws_secret_access_key"] = self.secret_access_key
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        return kwargs


class S3Client:
    """Thin async wrapper around the subset of S3 operations most services need."""

    def __init__(self, settings: AwsSettings, bucket: str):
        """Store settings/bucket; no connection is opened until a method is called."""
        self._settings = settings
        self._bucket = bucket
        self._session = aioboto3.Session()

    async def upload_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        """Upload raw bytes to `key` in this client's bucket."""
        extra_args = {"ContentType": content_type} if content_type else {}
        async with self._session.client("s3", **self._settings.session_kwargs()) as s3:
            await s3.put_object(Bucket=self._bucket, Key=key, Body=data, **extra_args)

    async def download_bytes(self, key: str) -> bytes:
        """Download and return the full contents of `key` as bytes."""
        async with self._session.client("s3", **self._settings.session_kwargs()) as s3:
            response = await s3.get_object(Bucket=self._bucket, Key=key)
            return await response["Body"].read()

    async def delete(self, key: str) -> None:
        """Delete `key` from this client's bucket."""
        async with self._session.client("s3", **self._settings.session_kwargs()) as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    async def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a time-limited, unauthenticated download URL for `key`.

        Args:
            key: Object key within this client's bucket.
            expires_in: URL lifetime in seconds (default 1 hour).
        """
        async with self._session.client("s3", **self._settings.session_kwargs()) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )

    async def health_check(self) -> bool:
        """Return True if the bucket is reachable (HEAD request), False on any error."""
        try:
            async with self._session.client("s3", **self._settings.session_kwargs()) as s3:
                await s3.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False
