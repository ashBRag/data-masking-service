"""Async AWS client: S3 only (aioboto3).

Self-contained: no dependency on any other libs/* package.
"""

from libs.aws.base import AwsSettings, S3Client

__all__ = ["AwsSettings", "S3Client"]
