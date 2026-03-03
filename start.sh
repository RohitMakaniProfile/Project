#!/bin/bash
set -e

# Render provides postgresql:// but SQLAlchemy async needs postgresql+asyncpg://
if [[ "$DATABASE_URL" == postgresql://* ]]; then
  export DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgresql://}"
fi
if [[ "$DATABASE_URL" == postgres://* ]]; then
  export DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgres://}"
fi

echo "Running database migrations..."
alembic upgrade head

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
