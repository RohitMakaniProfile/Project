"""ARQ background worker for async job processing."""
import asyncio
import uuid
from datetime import datetime, timezone

from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Job, JobStatus
from app.services.credits import refund_credits
from app.logging_config import get_logger

logger = get_logger(__name__)

# Module-level pool reference for enqueueing
_arq_pool: ArqRedis | None = None


def _parse_redis_url(url: str) -> RedisSettings:
    """Parse a redis:// URL into ARQ RedisSettings."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


async def get_arq_pool() -> ArqRedis:
    """Get or create the ARQ Redis connection pool."""
    global _arq_pool
    if _arq_pool is None:
        settings = get_settings()
        _arq_pool = await create_pool(_parse_redis_url(settings.REDIS_URL))
    return _arq_pool


async def close_arq_pool():
    """Close the ARQ Redis pool."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


async def enqueue_summarise_job(job_id: str):
    """Enqueue a summarise job for background processing."""
    pool = await get_arq_pool()
    await pool.enqueue_job("process_summarise", job_id)
    logger.info("job_enqueued", job_id=job_id)


async def process_summarise(ctx: dict, job_id: str):
    """
    ARQ worker function: processes a summarise job.
    - Marks the job as running
    - Performs the summarisation
    - Marks as completed or failed
    - Refunds credits on failure
    """
    logger.info("job_processing_started", job_id=job_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()

        if job is None:
            logger.error("job_not_found_in_worker", job_id=job_id)
            return

        # Mark as running
        job.status = JobStatus.running
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            # Simulate processing delay (real implementation would call an AI model)
            await asyncio.sleep(2)

            # Simple summarisation logic
            text = job.input_text
            sentences = [s.strip() for s in text.split(".") if s.strip()]
            word_count = len(text.split())

            if len(sentences) <= 2:
                summary = text
            else:
                # Take the first and last sentence as a naive summary
                summary = f"{sentences[0]}. {sentences[-1]}."

            job.status = JobStatus.completed
            job.result = f"Summary ({word_count} words → {len(summary.split())} words): {summary}"
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info("job_completed", job_id=job_id)

        except Exception as e:
            logger.error("job_processing_failed", job_id=job_id, error=str(e))

            job.status = JobStatus.failed
            job.error = f"Processing failed: {str(e)}"
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # Refund credits when background job fails
            if job.credit_transaction_id:
                await refund_credits(
                    db=db,
                    org_id=job.organisation_id,
                    user_id=job.user_id,
                    amount=10,  # SUMMARISE_COST
                    reason=f"Refund: summarise job {job_id} failed",
                )
                logger.info("job_credits_refunded", job_id=job_id)


# ARQ worker settings — used when running `arq app.worker.WorkerSettings`
class WorkerSettings:
    functions = [process_summarise]
    max_jobs = 10
    job_timeout = 300  # 5 minutes
    redis_settings = _parse_redis_url(get_settings().REDIS_URL)
    on_startup = None
    on_shutdown = None
