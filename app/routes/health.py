"""Health check endpoint."""
from datetime import datetime, timezone
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """
    GET /health — returns application status and confirms the database is reachable.
    Returns HTTP 503 if the database is unreachable.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy",
                "database": "reachable",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "unreachable",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
