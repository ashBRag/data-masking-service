"""Async AWS clients: S3 and SQS only (aioboto3).

Self-contained: no dependency on any other libs/* package.
"""

from libs.aws.base import AwsSettings, S3Client, SqsClient

__all__ = ["AwsSettings", "S3Client", "SqsClient"]
