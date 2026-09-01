"""Project-specific application settings.

Generic env/logging/rate-limit machinery lives in libs.config;
this file only adds fields and defaults specific to *this* project.
"""

from typing import Annotated

from pydantic import computed_field, field_validator
from pydantic_settings import NoDecode

from libs.config import BaseAppSettings, Environment

__all__ = ["Environment", "settings"]


class Settings(BaseAppSettings):
    """This project's settings: adds identity/API fields on top of the base."""

    PROJECT_NAME: str = "Data Masking Service"
    PROJECT_SLUG: str = "data-masking-service"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Masks sensitive fields in an XML document and uploads the result to S3"
    API_V1_STR: str = "/api/v1"

    # Per-route rate limits; "default" (from BaseAppSettings.RATE_LIMIT_DEFAULT)
    # applies to any route not listed here.
    RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = {
        "root": ["60 per minute"],
        "health": ["20 per minute"],
        "mask": ["20 per minute"],
    }

    # JWT auth for route access (see app/api/deps.py:require_scopes). Distinct
    # from JWT_SECRET_KEY/JWT_ALGORITHM (BaseAppSettings) which those two
    # fields are shared with - this service both issues logging context from
    # and authenticates requests with the same token.
    # JWT_ISSUER must come from the environment (no default) - it identifies
    # the auth service that signed the token, which varies per deployment.
    JWT_ISSUER: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def JWT_AUDIENCE(self) -> str:
        """Expected 'aud' claim - always PROJECT_SLUG, not independently configurable."""
        return self.PROJECT_SLUG

    # Postgres connection (see libs/db for the engine/session built from these).
    # Host/port/user/password var names match the shared infra stack's .env -
    # no separate app-only copies for those. POSTGRES_DB is the one exception:
    # this app uses its own dedicated database rather than the infra stack's
    # shared default, so it's set explicitly in .env.example/.env.<environment>
    # instead of inheriting infra's value.
    POSTGRES_HOST: str = "postgresql"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "data-masking-service"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_POOL_SIZE: int = 5
    POSTGRES_MAX_OVERFLOW: int = 10

    # Masked-document storage (see app/services/document_fetch.py,
    # app/api/v1/routes/masking.py, libs/aws.S3Client). Works against any
    # S3-compatible endpoint - AWS S3 (leave AWS_ENDPOINT_URL unset),
    # LocalStack for local dev, or Supabase Storage's S3-compatible API (set
    # AWS_ENDPOINT_URL to its endpoint and AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
    # to a Supabase storage access key pair, not your Supabase project's
    # anon/service key).
    S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_ENDPOINT_URL: str | None = None
    S3_PRESIGNED_URL_EXPIRY_SECONDS: int = 7 * 24 * 60 * 60  # 7 days

    # Inbound document fetch (POST /api/v1/mask fetches `document_url`
    # itself - see app/services/document_fetch.py). Bounds + SSRF guardrails
    # for that outbound request.
    DOCUMENT_FETCH_MAX_BYTES: int = 100 * 1024 * 1024  # 100MB
    DOCUMENT_FETCH_TIMEOUT_SECONDS: float = 30.0
    # Schemes allowed for `document_url`; deliberately excludes file://, ftp://, etc.
    DOCUMENT_FETCH_ALLOWED_SCHEMES: Annotated[list[str], NoDecode] = ["https"]

    @field_validator("DOCUMENT_FETCH_ALLOWED_SCHEMES", mode="before")
    @classmethod
    def _split_comma_separated_schemes(cls, value: object) -> object:
        """Accept a plain comma-separated env var value, not just a JSON array (see BaseAppSettings)."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


# Constructed once at import time and shared app-wide.
settings = Settings().apply_environment_defaults()
