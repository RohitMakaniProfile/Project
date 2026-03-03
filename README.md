# NexusAPI — Multi-Tenant Credit-Gated Backend

A production-grade multi-tenant, credit-gated backend API built with FastAPI, async SQLAlchemy, PostgreSQL, Redis, and ARQ.

## Architecture Overview

- **FastAPI** — async Python web framework
- **PostgreSQL** — primary database (async via asyncpg)
- **Redis** — rate limiting + background job queue
- **ARQ** — async background job processing
- **Alembic** — database migrations
- **JWT** — stateless authentication (signed with HS256)
- **Google OAuth 2.0** — user authentication

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/nexusapi` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | Secret key for signing JWT tokens | `your-random-secret-key-here` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `JWT_EXPIRY_HOURS` | JWT token expiry in hours | `24` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | `xxxx.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | `GOCSPX-xxxx` |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | `http://localhost:8000/auth/callback` |
| `APP_ENV` | Environment (development/production) | `development` |
| `APP_HOST` | Bind host | `0.0.0.0` |
| `APP_PORT` | Bind port | `8000` |
| `RATE_LIMIT_PER_MINUTE` | Max requests per org per minute | `60` |

## How to Run Locally

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/nexusapi.git
cd nexusapi
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
# Edit .env with your actual values (database, Redis, Google OAuth credentials)
```

### 5. Create the PostgreSQL database

```bash
createdb nexusapi
```

### 6. Run database migrations

```bash
alembic upgrade head
```

### 7. Start the API server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 8. Start the background worker (separate terminal)

```bash
arq app.worker.WorkerSettings
```

## How to Run with Docker

```bash
docker-compose up --build
```

This starts PostgreSQL, Redis, the API server, and the ARQ worker.

## Example API Calls

### Health Check

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{"status": "healthy", "database": "reachable", "timestamp": "2026-03-02T10:00:00+00:00"}
```

### Grant Credits (admin)

```bash
curl -X POST http://localhost:8000/credits/grant \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "reason": "Initial credit allocation"}'
```

**Response:**
```json
{"message": "Granted 100 credits", "balance": 100, "transaction_id": "uuid"}
```

### Check Balance

```bash
curl http://localhost:8000/credits/balance \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{"organisation_id": "uuid", "balance": 100, "recent_transactions": [...]}
```

### Analyse Text (synchronous, costs 25 credits)

```bash
curl -X POST http://localhost:8000/api/analyse \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "The quick brown fox jumps over the lazy dog near the riverbank"}'
```

**Response:**
```json
{"result": "Analysis complete. Word count: 11. Unique words: 11.", "credits_remaining": 75}
```

### Summarise Text (async, costs 10 credits)

```bash
curl -X POST http://localhost:8000/api/summarise \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "The quick brown fox jumps over the lazy dog. The dog was sleeping peacefully. The fox continued on its journey."}'
```

**Response:**
```json
{"job_id": "uuid", "credits_remaining": 65}
```

### Poll Job Status

```bash
curl http://localhost:8000/api/jobs/JOB_ID_HERE \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{"job_id": "uuid", "status": "completed", "result": "Summary (19 words → 13 words): ...", "error": null, "created_at": "..."}
```

### Analyse with Idempotency Key

```bash
curl -X POST http://localhost:8000/api/analyse \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-request-id-123" \
  -d '{"text": "The quick brown fox jumps over the lazy dog near the riverbank"}'
```

Sending the same request with the same Idempotency-Key will return the original response without deducting credits again.

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Health check (200 healthy, 503 unhealthy) |
| GET | `/auth/google` | None | Initiates Google OAuth flow |
| GET | `/auth/callback` | None | Google OAuth callback, returns JWT |
| GET | `/me` | JWT | Returns user profile and organisation |
| GET | `/credits/balance` | JWT | Organisation credit balance + last 10 txns |
| POST | `/credits/grant` | Admin | Add credits to organisation |
| POST | `/api/analyse` | JWT | Synchronous analysis (25 credits) |
| POST | `/api/summarise` | JWT | Async summarisation (10 credits) |
| GET | `/api/jobs/{job_id}` | JWT | Poll background job status |

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py             # Settings from environment variables
│   ├── database.py           # Async SQLAlchemy engine and session
│   ├── models.py             # ORM models (Organisation, User, CreditTransaction, Job)
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── auth.py               # JWT creation, validation, dependencies
│   ├── exceptions.py         # Custom exceptions
│   ├── logging_config.py     # Structured JSON logging
│   ├── redis_client.py       # Redis connection management
│   ├── worker.py             # ARQ background worker
│   ├── middleware/
│   │   ├── rate_limit.py     # Per-org rate limiting via Redis
│   │   └── logging_middleware.py  # Request logging middleware
│   ├── routes/
│   │   ├── health.py         # GET /health
│   │   ├── auth_routes.py    # OAuth + /me
│   │   ├── credits.py        # Credit grant + balance
│   │   └── products.py       # /api/analyse, /api/summarise, /api/jobs
│   └── services/
│       └── credits.py        # Credit ledger service (deduct, grant, refund)
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 2026_03_02_001_initial_schema.py
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── DECISIONS.md
└── README.md
```
