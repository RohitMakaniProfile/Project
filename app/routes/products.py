"""Product endpoints: /api/analyse (sync) and /api/summarise (async)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db, AsyncSessionLocal
from app.exceptions import InsufficientCreditsError, IdempotencyConflictError
from app.models import Job, JobStatus, User
from app.schemas import (
    AnalyseRequest,
    AnalyseResponse,
    JobStatusResponse,
    SummariseRequest,
    SummariseResponse,
)
from app.services.credits import (
    check_and_get_existing_idempotent_response,
    deduct_credits,
    get_balance,
    refund_credits,
)
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["products"])

ANALYSE_COST = 25
SUMMARISE_COST = 10


@router.post("/analyse")
async def analyse(
    request: Request,
    body: AnalyseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    POST /api/analyse — synchronous product endpoint. Costs 25 credits.
    Accepts optional Idempotency-Key header.
    """
    # --- Idempotency check ---
    if idempotency_key:
        existing_txn = await check_and_get_existing_idempotent_response(
            db, user.organisation_id, idempotency_key
        )
        if existing_txn:
            # Return cached result — do NOT deduct credits again
            balance = await get_balance(db, user.organisation_id)
            # Replay the same analysis
            words = body.text.split()
            word_count = len(words)
            unique_words = len(set(w.lower() for w in words))
            return AnalyseResponse(
                result=f"Analysis complete. Word count: {word_count}. Unique words: {unique_words}.",
                credits_remaining=balance,
            )

    # --- Deduct credits ---
    try:
        txn, remaining = await deduct_credits(
            db=db,
            org_id=user.organisation_id,
            user_id=user.id,
            amount=ANALYSE_COST,
            reason="API call: /api/analyse",
            idempotency_key=idempotency_key,
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "insufficient_credits",
                "balance": e.balance,
                "required": ANALYSE_COST,
            },
        )
    except IdempotencyConflictError:
        # Race condition: another concurrent request with same key just completed.
        # Fetch the balance and return the result.
        balance = await get_balance(db, user.organisation_id)
        words = body.text.split()
        word_count = len(words)
        unique_words = len(set(w.lower() for w in words))
        return AnalyseResponse(
            result=f"Analysis complete. Word count: {word_count}. Unique words: {unique_words}.",
            credits_remaining=balance,
        )

    # --- Processing ---
    try:
        words = body.text.split()
        word_count = len(words)
        unique_words = len(set(w.lower() for w in words))
        result = f"Analysis complete. Word count: {word_count}. Unique words: {unique_words}."
    except Exception as e:
        # Processing failed after deduction — refund the credits
        logger.error("analyse_processing_failed", error=str(e), org_id=str(user.organisation_id))
        await refund_credits(
            db=db,
            org_id=user.organisation_id,
            user_id=user.id,
            amount=ANALYSE_COST,
            reason="Refund: /api/analyse processing failed",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "processing_failed",
                "message": "Analysis processing failed. Credits have been refunded.",
                "request_id": str(request.state.request_id),
            },
        )

    await db.commit()
    return AnalyseResponse(result=result, credits_remaining=remaining)


@router.post("/summarise")
async def summarise(
    request: Request,
    body: SummariseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    POST /api/summarise — async product endpoint. Costs 10 credits.
    Returns a job_id immediately; processing happens in the background.
    """
    # --- Idempotency check ---
    if idempotency_key:
        existing_txn = await check_and_get_existing_idempotent_response(
            db, user.organisation_id, idempotency_key
        )
        if existing_txn:
            # Find the associated job
            result = await db.execute(
                select(Job).where(
                    Job.idempotency_key == idempotency_key,
                    Job.organisation_id == user.organisation_id,
                )
            )
            existing_job = result.scalar_one_or_none()
            if existing_job:
                balance = await get_balance(db, user.organisation_id)
                return SummariseResponse(
                    job_id=existing_job.id, credits_remaining=balance
                )

    # --- Deduct credits ---
    try:
        txn, remaining = await deduct_credits(
            db=db,
            org_id=user.organisation_id,
            user_id=user.id,
            amount=SUMMARISE_COST,
            reason="API call: /api/summarise",
            idempotency_key=idempotency_key,
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "insufficient_credits",
                "balance": e.balance,
                "required": SUMMARISE_COST,
            },
        )
    except IdempotencyConflictError:
        # Race condition with duplicate key — find the existing job
        result = await db.execute(
            select(Job).where(
                Job.idempotency_key == idempotency_key,
                Job.organisation_id == user.organisation_id,
            )
        )
        existing_job = result.scalar_one_or_none()
        if existing_job:
            balance = await get_balance(db, user.organisation_id)
            return SummariseResponse(
                job_id=existing_job.id, credits_remaining=balance
            )
        # If no job found (edge case), re-raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "idempotency_conflict",
                "message": "This idempotency key has already been used.",
                "request_id": str(request.state.request_id),
            },
        )

    # --- Create job record ---
    job = Job(
        id=uuid.uuid4(),
        organisation_id=user.organisation_id,
        user_id=user.id,
        status=JobStatus.pending,
        input_text=body.text,
        credit_transaction_id=txn.id,
        idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.commit()

    # --- Enqueue background job via ARQ ---
    from app.worker import enqueue_summarise_job

    try:
        await enqueue_summarise_job(str(job.id))
    except Exception as e:
        logger.error("job_enqueue_failed", job_id=str(job.id), error=str(e))
        # Job is created but enqueue failed. Mark as failed and refund.
        job.status = JobStatus.failed
        job.error = "Failed to enqueue background job"
        await db.commit()
        await refund_credits(
            db=db,
            org_id=user.organisation_id,
            user_id=user.id,
            amount=SUMMARISE_COST,
            reason=f"Refund: failed to enqueue summarise job {job.id}",
        )

    return SummariseResponse(job_id=job.id, credits_remaining=remaining)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    request: Request,
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/jobs/{job_id} — polls job status.
    Only the organisation that created the job may retrieve its result.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "job_not_found",
                "message": f"No job found with ID {job_id}.",
                "request_id": str(request.state.request_id),
            },
        )

    # Enforce tenant isolation: only the owning organisation can see the job
    if job.organisation_id != user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "job_not_found",
                "message": f"No job found with ID {job_id}.",
                "request_id": str(request.state.request_id),
            },
        )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
    )
