# Data Masking Service

A standalone service that masks sensitive fields in an XML document and
uploads the masked result to S3.

## Pipeline

```
document_url + masking_policy_id
  │
  ▼
Generate id        a fresh document id is generated for this run
  │                (no document table here to source one from)
  ▼
Look up policy    MaskingPolicy row (must be is_active=True)
  │
  ▼
Fetch              document_url fetched via HTTPS GET
  │                (SSRF-guarded: scheme + resolved-IP validated,
  │                 response streamed with a size cap)
  ▼
Parse              defusedxml, namespace-aware (XXE-safe)
  │
  ▼
Mask               deterministic per-field tokenization (SHA-256-based) -
  │                same value always maps to the same token; original
  │                values are stored separately (mask_tokens), never
  │                logged
  ▼
Persist tokens     mask_tokens (Postgres), upserted on (document_id, token)
  │                so re-masking the same document id is idempotent
  ▼
Upload             masked XML uploaded to S3 at masked/{document_id}.xml
  │                (re-masking the same document id overwrites its
  │                 previous masked file)
  ▼
Return             document id + presigned S3 URL to the masked file
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/mask` | Fetches `document_url`, masks it per `masking_policy_id`, uploads the result to S3, and returns the generated document id, a presigned URL to the masked file, and masking stats. |

## Project layout

```
app/
  main.py             # Wires everything together with this project's settings/routes
  core/                 # Settings, rate limiter
  api/deps.py            # Shared FastAPI dependency providers (DB session, S3 client, pipeline service)
  api/v1/routes/         # mask
  models/                # SQLModel tables: MaskingPolicy, MaskToken
  schemas/               # Request/response shapes + the internal MaskingResult
  services/               # MaskingService, TokenPersistenceService, MaskPipelineService

libs/                    # Small, reusable, project-agnostic infra helpers
                          # (Postgres/S3 client, logging, metrics, errors,
                          #  XML/tokenization utilities, SSRF-guarded HTTP fetch, ...)

scripts/                 # Seed script for masking policies
tests/                   # Unit tests (http fetch SSRF guardrails, mask pipeline orchestration)
```

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)
- Docker (Postgres - see `docker-compose.yml`)
- An S3-compatible bucket (AWS S3, LocalStack, or Supabase Storage)

## Setup

```bash
make install                        # uv sync
cp .env.example .env.development    # fill in real values (JWT secret, Postgres, S3, ...)
```

## Running

```bash
make dev     # uvicorn with reload, port 8000
make prod    # uvicorn, no reload
```

Or directly:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Check it's up:

- `GET /` - basic service info
- `GET /health` - liveness + Postgres/S3 connectivity (`degraded`/503 if either is unreachable)
- `GET /docs` - Swagger UI
- `GET /metrics` - Prometheus scrape endpoint

## Seeding

```bash
uv run python scripts/seed_masking_policies.py   # active masking policy
```

## Docker

```bash
make docker-up     # creates backend-internal if missing, builds, starts (ENV=development by default)
make docker-logs
make docker-down
```

Pass `ENV=staging` / `ENV=production` to target a different `.env.<ENV>` file.

## Configuration

Settings are loaded via `pydantic-settings` from `.env.<APP_ENV>` (falling back to
`.env.local` / `.env`), with environment-specific defaults applied on top - see
`app/core/config.py` for this project's fields. See `.env.example` for the full
list of variables.

## Linting & tests

```bash
make lint     # ruff check
make format   # ruff format
make test     # pytest
```
